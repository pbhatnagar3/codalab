"""
Defines deployment commands.
"""

import datetime
import logging
import logging.config
import os
from os.path import (abspath,
                     dirname)
import sys

# Add codalabtools to the module search path
sys.path.append(dirname(dirname(dirname(abspath(__file__)))))

from StringIO import StringIO
from fabric.api import (cd,
                        env,
                        execute,
                        get,
                        prefix,
                        put,
                        require,
                        task,
                        roles,
                        require,
                        run,
                        settings,
                        shell_env,
                        sudo)
from fabric.contrib.files import exists
from fabric.network import ssh
from fabric.utils import fastprint
from codalabtools.deploy import DeploymentConfig, Deployment


logger = logging.getLogger('codalabtools')

# Uncomment for extra logging
# ssh.util.log_to_file("paramiko.log", 10)

#
# Internal helpers
#

def _validate_asset_choice(choice):
    """
    Translate the choice string into a list of assets. See Deploy and Teardown functions.

    choice: One of 'all', 'build' or 'web'.
    """
    if choice == 'all':
        assets = {'build', 'web'}
    elif choice == 'build':
        assets = {'build'}
    elif choice == 'web':
        assets = {'web'}
    else:
        raise ValueError("Invalid choice: %s. Valid choices are: 'build', 'web' or 'all'." % (choice))
    return assets

def provision_packages(packages=None):
    """
    Installs a set of packages on a host machine.

    packages: A string listing the packages which will get installed with the command:
        sudo apt-get -y install <packages>
    """
    sudo('apt-get update')
    sudo('apt-get -y install %s' % packages)
    sudo('apt-get install python-tk')
    sudo('easy_install pip')
    sudo('pip install -U --force-reinstall setuptools')
    sudo('pip install -U --force-reinstall virtualenvwrapper')
    sudo('pip install -U --force-reinstall wheel')
    sudo('pip install numpy')
    sudo('pip install matplotlib')

#
# Tasks for reading configuration information.
#

@task
def using(path):
    """
    Specifies a location for the CodaLab configuration file.
    """
    env.cfg_path = path

@task
def config(label=None):
    """
    Reads deployment parameters for the given setup.

    label: Label identifying the desired setup.
    """
    env.cfg_label = label
    print "Deployment label is: ", env.cfg_label
    filename = ".codalabconfig"
    if 'cfg_path' not in env:
        env.cfg_path = os.path.join(os.getcwd(), filename)
        if os.path.exists(env.cfg_path) == False:
            env.cfg_path = os.path.join(os.path.expanduser("~"), filename)
    print "Loading configuration from: ", env.cfg_path
    configuration = DeploymentConfig(label, env.cfg_path)
    print "Configuring logger..."
    logging.config.dictConfig(configuration.getLoggerDictConfig())
    logger.info("Loaded configuration from file: %s", configuration.getFilename())

    env.user = configuration.getVirtualMachineLogonUsername()
    env.password = configuration.getVirtualMachineLogonPassword()
    env.key_filename = configuration.getServiceCertificateKeyFilename()
    env.roledefs = {'build' : [configuration.getBuildHostname()]}

    if label is not None:
        env.roledefs.update({'web' : configuration.getWebHostnames()})
        # Information about main CodaLab repo
        env.git_user = configuration.getGitUser()
        env.git_repo = configuration.getGitRepo()
        env.git_tag = configuration.getGitTag()
        env.git_repo_url = 'https://github.com/{0}/{1}.git'.format(env.git_user, env.git_repo)
        # Information about Bundles repo
        env.git_bundles_user = configuration.getBundleServiceGitUser()
        env.git_bundles_repo = configuration.getBundleServiceGitRepo()
        env.git_bundles_tag = configuration.getBundleServiceGitTag()
        if len(configuration.getBundleServiceUrl()) > 0:
            env.git_bundles_repo_url = 'https://github.com/{0}/{1}.git'.format(env.git_bundles_user, env.git_bundles_repo)
        else:
            env.git_bundles_repo_url = ''
        env.deploy_dir = 'deploy'
        env.build_archive = '{0}.tar.gz'.format(env.git_tag)
        env.django_settings_module = 'codalab.settings'
        env.django_configuration = configuration.getDjangoConfiguration()
        env.config_http_port = '80'
        env.config_server_name = "{0}.cloudapp.net".format(configuration.getServiceName())

    env.configuration = True

#
# Tasks for provisioning machines
#

@task
@roles('build')
def provision_build():
    """
    Installs required software packages on a newly provisioned build machine.
    """
    packages = ('build-essential python-crypto python2.7-dev python-setuptools ' +
                'libmysqlclient-dev mysql-client-core-5.5 ' +
                'libpcre3-dev libpng12-dev libjpeg-dev git')
    provision_packages(packages)

@task
@roles('web')
def provision_web():
    """
    Installs required software packages on a newly provisioned web instance.
    """
    packages = ('language-pack-en python2.7 python-setuptools libmysqlclient18 ' +
                'libpcre3 libjpeg8 libpng3 nginx supervisor git python2.7-dev ' +
                'libmysqlclient-dev mysql-client-core-5.5 uwsgi-plugin-python')
    provision_packages(packages)

@task
def provision(choice):
    """
    Provisions specified assets in the deployment.

    choice: Indicates which assets to provision:
        'build' -> provision the build machine
        'web'   -> provision the web instances
        'all'   -> provision everything
    """
    assets = _validate_asset_choice(choice)
    require('configuration')
    logger.info("Provisioning begins: %s.", assets)
    configuration = DeploymentConfig(env.cfg_label, env.cfg_path)
    dep = Deployment(configuration)
    dep.Deploy(assets)
    if 'build' in assets:
        logger.info("Installing sofware on the build machine.")
        execute(provision_build)
    if 'web' in assets:
        logger.info("Installing sofware on web instances.")
        execute(provision_web)
    logger.info("Provisioning is complete.")

@task
def teardown(choice):
    """
    Deletes specified assets in the deployment. Be careful: there is no undoing!

    choice: Indicates which assets to delete:
        'build' -> provision the build machine
        'web'   -> provision the web instances
        'all'   -> provision everything
    """
    assets = _validate_asset_choice(choice)
    require('configuration')
    logger.info("Teardown begins: %s.", assets)
    configuration = DeploymentConfig(env.cfg_label, env.cfg_path)
    dep = Deployment(configuration)
    dep.Teardown(assets)
    logger.info("Teardown is complete.")

@task
@roles('build', 'web')
def test_connections():
    """
    Verifies that we can connect to all instances.
    """
    require('configuration')
    sudo('hostname')

#
# Tasks for creating and installing build artifacts
#

@roles("build")
@task
def build():
    """
    Builds artifacts to install on the deployment instances.
    """
    require('configuration')

    # Assemble source and configurations for the web site
    build_dir = "/".join(['builds', env.git_user, env.git_repo])
    src_dir = "/".join([build_dir, env.git_tag])
    if exists(src_dir):
        run('rm -rf %s' % (src_dir.rstrip('/')))
    with settings(warn_only=True):
        run('mkdir -p %s' % src_dir)
    with cd(src_dir):
        # TODO: why do we have the --branch and --single-branch tags here, this causes problems
        run('git clone --depth=1 --branch %s --single-branch %s .' % (env.git_tag, env.git_repo_url))
        # Generate settings file (local.py)
        configuration = DeploymentConfig(env.cfg_label, env.cfg_path)
        dep = Deployment(configuration)
        buf = StringIO()
        buf.write(dep.getSettingsFileContent())
        settings_file = "/".join(['codalab', 'codalab', 'settings', 'local.py'])
        put(buf, settings_file)
    # Assemble source and configurations for the bundle service
    if len(env.git_bundles_repo_url) > 0:
        build_dir_b = "/".join(['builds', env.git_bundles_user, env.git_bundles_repo])
        src_dir_b = "/".join([build_dir_b, env.git_bundles_tag])
        if exists(src_dir_b):
            run('rm -rf %s' % (src_dir_b.rstrip('/')))
        with settings(warn_only=True):
            run('mkdir -p %s' % src_dir_b)
        with cd(src_dir_b):
            # TODO: why do we have the --branch and --single-branch tags here, this causes problems
            run('git clone --depth=1 --branch %s --single-branch %s .' % (env.git_bundles_tag, env.git_bundles_repo_url))
        # Replace current bundles dir in main CodaLab other bundles repo.
        bundles_dir = "/".join([src_dir, 'bundles'])
        run('rm -rf %s' % (bundles_dir.rstrip('/')))
        run('mv %s %s' % (src_dir_b, bundles_dir))
    # Package everything
    with cd(build_dir):
        run('rm -f %s' % env.build_archive)
        run('tar -cvf - %s | gzip -9 -c > %s' % (env.git_tag, env.build_archive))

@roles("build")
@task
def push_build():
    """
    Pushes the output of the build task to the instances where the build artifacts will be installed.
    """
    require('configuration')
    build_dir = "/".join(['builds', env.git_user, env.git_repo])
    with cd(build_dir):
        for host in env.roledefs['web']:
            parts = host.split(':', 1)
            host = parts[0]
            port = parts[1]
            run('scp -P {0} {1} {2}@{3}:{4}'.format(port, env.build_archive, env.user, host, env.build_archive))

@roles('web')
@task
def deploy_web():
    """
    Installs the output of the build on the web instances.
    """
    require('configuration')
    if exists(env.deploy_dir):
        run('rm -rf %s' % env.deploy_dir)
    run('tar -xvzf %s' % env.build_archive)
    run('mv %s deploy' % env.git_tag)

    run('source /usr/local/bin/virtualenvwrapper.sh && mkvirtualenv venv')
    env.SHELL_ENV = dict(
        DJANGO_SETTINGS_MODULE=env.django_settings_module,
        DJANGO_CONFIGURATION=env.django_configuration,
        CONFIG_HTTP_PORT=env.config_http_port,
        CONFIG_SERVER_NAME=env.config_server_name)
    print env.SHELL_ENV
    with cd(env.deploy_dir):
        with prefix('source /usr/local/bin/virtualenvwrapper.sh && workon venv'), shell_env(**env.SHELL_ENV):
            requirements_path = "/".join(['codalab', 'requirements', 'dev_azure_nix.txt'])
            pip_cmd = 'pip install -r {0}'.format(requirements_path)
            run(pip_cmd)
            # additional requirements for bundle service
            run('pip install SQLAlchemy simplejson')
            with cd('codalab'):
                run('python manage.py config_gen')
                run('mkdir -p ~/.codalab && cp ./config/generated/bundle_server_config.json ~/.codalab/config.json')
                run('python manage.py syncdb --migrate')
                run('python scripts/initialize.py')
                run('python manage.py collectstatic --noinput')
                sudo('ln -sf `pwd`/config/generated/nginx.conf /etc/nginx/sites-enabled/codalab.conf')
                sudo('ln -sf `pwd`/config/generated/supervisor.conf /etc/supervisor/conf.d/codalab.conf')

                # Setup new relic
                cfg = DeploymentConfig(env.cfg_label, env.cfg_path)
                run('newrelic-admin generate-config %s newrelic.ini' % cfg.getNewRelicKey())

@roles('web')
@task
def install_mysql(choice='all'):
    """
    Installs a local instance of MySQL of the web instance. This will only work
    if the number of web instances is one.

    choice: Indicates which assets to create/install:
        'mysql'      -> just install MySQL; don't create the databases
        'site_db'    -> just create the site database
        'bundles_db' -> just create the bundle service database
        'all' or ''  -> install all three
    """
    require('configuration')
    if len(env.roledefs['web']) != 1:
        raise Exception("Task install_mysql requires exactly one web instance.")

    if choice == 'mysql':
        choices = {'mysql'}
    elif choice == 'site_db':
        choices = {'site_db'}
    elif choice == 'bundles_db':
        choices = {'bundles_db'}
    elif choice == 'all':
        choices = {'mysql', 'site_db', 'bundles_db'}
    elif choice == 'bundles_db_recreate':
        choices = {'bundles_db_recreate'}
    else:
        raise ValueError("Invalid choice: %s. Valid choices are: 'build', 'web' or 'all'." % (choice))

    configuration = DeploymentConfig(env.cfg_label, env.cfg_path)
    dba_password = configuration.getDatabaseAdminPassword()

    if 'mysql' in choices:
        sudo('DEBIAN_FRONTEND=noninteractive apt-get -q -y install mysql-server')
        sudo('mysqladmin -u root password {0}'.format(dba_password))

    if 'site_db' in choices:
        db_name = configuration.getDatabaseName()
        db_user = configuration.getDatabaseUser()
        db_password = configuration.getDatabasePassword()
        cmds = ["create database {0};".format(db_name),
                "create user '{0}'@'localhost' IDENTIFIED BY '{1}';".format(db_user, db_password),
                "GRANT ALL PRIVILEGES ON {0}.* TO '{1}'@'localhost' WITH GRANT OPTION;".format(db_name, db_user)]
        run('mysql --user=root --password={0} --execute="{1}"'.format(dba_password, " ".join(cmds)))

    if 'bundles_db' in choices:
        db_name = configuration.getBundleServiceDatabaseName()
        db_user = configuration.getBundleServiceDatabaseUser()
        db_password = configuration.getBundleServiceDatabasePassword()
        cmds = ["create database {0};".format(db_name),
                "create user '{0}'@'localhost' IDENTIFIED BY '{1}';".format(db_user, db_password),
                "GRANT ALL PRIVILEGES ON {0}.* TO '{1}'@'localhost' WITH GRANT OPTION;".format(db_name, db_user)]
        run('mysql --user=root --password={0} --execute="{1}"'.format(dba_password, " ".join(cmds)))

    if 'bundles_db_recreate' in choices:
        db_name = configuration.getBundleServiceDatabaseName()
        db_user = configuration.getBundleServiceDatabaseUser()
        db_password = configuration.getBundleServiceDatabasePassword()
        cmds = ["drop database {0};".format(db_name),
                "create database {0};".format(db_name),
                "GRANT ALL PRIVILEGES ON {0}.* TO '{1}'@'localhost' WITH GRANT OPTION;".format(db_name, db_user)]
        run('mysql --user=root --password={0} --execute="{1}"'.format(dba_password, " ".join(cmds)))

@roles('web')
@task
def install_ssl_certificates():
    """
    Installs SSL certificates on the web instance.
    """
    require('configuration')
    cfg = DeploymentConfig(env.cfg_label, env.cfg_path)
    if (len(cfg.getSslCertificateInstalledPath()) > 0) and (len(cfg.getSslCertificateKeyInstalledPath()) > 0):
        put(cfg.getSslCertificatePath(), cfg.getSslCertificateInstalledPath(), use_sudo=True)
        put(cfg.getSslCertificateKeyPath(), cfg.getSslCertificateKeyInstalledPath(), use_sudo=True)
    else:
        logger.info("Skipping certificate installation because both files are not specified.")

@roles('web')
@task
def supervisor():
    """
    Starts the supervisor on the web instances.
    """
    with cd(env.deploy_dir):
        with prefix('source /usr/local/bin/virtualenvwrapper.sh && workon venv'):
            run('supervisord -c codalab/config/generated/supervisor.conf')

@roles('web')
@task
def supervisor_stop():
    """
    Stops the supervisor on the web instances.
    """
    with cd(env.deploy_dir):
        with prefix('source /usr/local/bin/virtualenvwrapper.sh && workon venv'):
            run('supervisorctl -c codalab/config/generated/supervisor.conf stop all')
            run('supervisorctl -c codalab/config/generated/supervisor.conf shutdown')
    # since worker is muli threaded, we need to kill all running processes
    with settings(warn_only=True):
        run('pkill -9 -f worker.py')

@roles('web')
@task
def supervisor_restart():
    """
    Restarts the supervisor on the web instances.
    """
    with cd(env.deploy_dir):
        with prefix('source /usr/local/bin/virtualenvwrapper.sh && workon venv'):
            run('supervisorctl -c codalab/config/generated/supervisor.conf restart all')

@roles('web')
@task
def nginx_restart():
    """
    Restarts nginx on the web instances.
    """
    sudo('/etc/init.d/nginx restart')

#
# Maintenance and diagnostics
#
@roles('web')
@task
def maintenance(mode):
    """
    Begin or end maintenance (mode=begin|end).
    """
    modes = {'begin': '1', 'end' : '0'}
    if mode in modes:
        require('configuration')
        env.SHELL_ENV = dict(
            DJANGO_SETTINGS_MODULE=env.django_settings_module,
            DJANGO_CONFIGURATION=env.django_configuration,
            CONFIG_HTTP_PORT=env.config_http_port,
            CONFIG_SERVER_NAME=env.config_server_name,
            MAINTENANCE_MODE=modes[mode])
        with cd(env.deploy_dir):
            with prefix('source /usr/local/bin/virtualenvwrapper.sh && workon venv'), shell_env(**env.SHELL_ENV):
                with cd('codalab'):
                    run('python manage.py config_gen')
                    sudo('ln -sf `pwd`/config/generated/nginx.conf /etc/nginx/sites-enabled/codalab.conf')
                    nginx_restart()
    else:
        print "Invalid mode. Valid values are 'begin' or 'end'"


@roles('web')
@task
def fetch_logs():
    """
    Fetch logs from the web instances into ~/logs.
    """
    require('configuration')
    with cd(env.deploy_dir):
        get('codalab/var/*.log', '~/logs/%(host)s/%(path)s')

@task
def enable_cors():
    """
    Enable cross-origin resource sharing for a Windows Azure storage service.
    """
    require('configuration')
    cfg = DeploymentConfig(env.cfg_label, env.cfg_path)
    dep = Deployment(cfg)
    dep.ensureStorageHasCorsConfiguration()

@task
def install_packages_compute_workers():
    # --yes and --force-yes accepts the Y/N question when installing the package
    sudo('apt-get update')
    sudo('apt-get --yes --force-yes install libsm6 openjdk-7-jre')
    sudo('apt-get --yes --force-yes install r-base')
    sudo('apt-get --yes --force-yes --fix-missing install mono-runtime libmono-system-web-extensions4.0-cil libmono-system-io-compression4.0-cil')

    # check for khiops dir if not, put
    if not exists("/home/azureuser/khiops/"):
        run('mkdir -p /home/azureuser/khiops/')
        put("~/khiops/", "/home/azureuser/") # actually ends up in /home/azureuser/khiops
        sudo("chmod +x /home/azureuser/khiops/bin/64/MODL")

@task
def khiops_print_machine_name_and_id():
    sudo("chmod +x /home/azureuser/khiops/bin/64/MODL")
    sudo("chmod +x /home/azureuser/khiops/get_license_info.sh")
    with cd('/home/azureuser/khiops/'):
        run("./get_license_info.sh")


@roles('web')
@task
def verify_all_emails():
    env.SHELL_ENV = dict(
        DJANGO_SETTINGS_MODULE=env.django_settings_module,
        DJANGO_CONFIGURATION=env.django_configuration,
        CONFIG_HTTP_PORT=env.config_http_port,
        CONFIG_SERVER_NAME=env.config_server_name,)
    with cd(env.deploy_dir):
        with prefix('source /usr/local/bin/virtualenvwrapper.sh && workon venv'), shell_env(**env.SHELL_ENV):
            with cd('codalab'):
                run('python manage.py verify_all_current_emails')


@roles('web')
@task
def get_database_dump():
    '''Saves backups to $CODALAB_MYSQL_BACKUP_DIR/launchdump-year-month-day-hour-min-second.sql.gz'''
    require('configuration')
    configuration = DeploymentConfig(env.cfg_label, env.cfg_path)
    db_host = "localhost"
    db_name = configuration.getDatabaseName()
    db_user = configuration.getDatabaseUser()
    db_password = configuration.getDatabasePassword()

    dump_file_name = 'launchdump-%s.sql.gz' % datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')

    run('mysqldump --host=%s --user=%s --password=%s %s --port=3306 | gzip > /tmp/%s' % (
        db_host,
        db_user,
        db_password,
        db_name,
        dump_file_name)
    )

    backup_dir = os.environ.get("CODALAB_MYSQL_BACKUP_DIR", "")
    get('/tmp/%s' % dump_file_name, backup_dir)


@task
def update_compute_worker():
    run('cd codalab && git pull --rebase')
    sudo("stop codalab-compute-worker")
    sudo("stop codalab-monitor")
    sudo("start codalab-compute-worker")
    sudo("start codalab-monitor")


@task
def update_filemode_to_false():
    run('cd codalab && git config core.filemode false')


@task
def update_conda():
    with settings(warn_only=True):
        if not run('conda'):
            # If we can't run conda add it to the path
            run('echo "export PATH=~/anaconda/bin:$PATH" >> ~/.bashrc')
    run('conda update --yes --prefix /home/azureuser/anaconda anaconda')


@roles('web')
@task
def deploy():
    maintenance("begin")
    supervisor_stop()
    env_prefix, env_shell = setup_env()
    with env_prefix, env_shell, cd('deploy/codalab'):
        run('git pull')
        run('pip install -r requirements/dev_azure_nix.txt')
        run('python manage.py syncdb --migrate')
        run('python manage.py collectstatic --noinput')

        # Generate config
        run('python manage.py config_gen')
        run('mkdir -p ~/.codalab && cp ./config/generated/bundle_server_config.json ~/.codalab/config.json')
        sudo('ln -sf `pwd`/config/generated/nginx.conf /etc/nginx/sites-enabled/codalab.conf')
        sudo('ln -sf `pwd`/config/generated/supervisor.conf /etc/supervisor/conf.d/codalab.conf')
        # run('python scripts/initialize.py')  # maybe not needed

        # Setup new relic
        cfg = DeploymentConfig(env.cfg_label, env.cfg_path)
        run('newrelic-admin generate-config %s newrelic.ini' % cfg.getNewRelicKey())

    # Setup bundle service for worksheets
    env_prefix, env_shell = setup_env()
    with env_prefix, env_shell, cd('deploy/bundles'):
        run('git pull')
        run('alembic upgrade head')

    supervisor()
    maintenance("end")


@task
def add_swap_config_and_restart():
    sudo('echo "ResourceDisk.Format=y" >> /etc/waagent.conf')
    sudo('echo "ResourceDisk.Filesystem=ext4" >> /etc/waagent.conf')
    sudo('echo "ResourceDisk.MountPoint=/mnt/resource" >> /etc/waagent.conf')
    sudo('echo "ResourceDisk.EnableSwap=y" >> /etc/waagent.conf')
    sudo('echo "ResourceDisk.SwapSizeMB=2048" >> /etc/waagent.conf')

    with settings(warn_only=True):
        sudo("umount /mnt")
        sudo("service walinuxagent restart")


@task
def setup_compute_worker_and_monitoring():
    '''
    For monitoring make sure the azure instance has the port 8000 forwarded
    '''
    password = os.environ.get('CODALAB_COMPUTE_MONITOR_PASSWORD', None)
    assert password, "CODALAB_COMPUTE_MONITOR_PASSWORD environment variable required to setup compute workers!"

    run("source /home/azureuser/venv/bin/activate && pip install bottle==0.12.8")

    put(
        local_path='configs/upstart/codalab-compute-worker.conf',
        remote_path='/etc/init/codalab-compute-worker.conf',
        use_sudo=True
    )
    put(
        local_path='configs/upstart/codalab-monitor.conf',
        remote_path='/etc/init/codalab-monitor.conf',
        use_sudo=True
    )
    run("echo %s > /home/azureuser/codalab/codalab/codalabtools/compute/password.txt" % password)

    with settings(warn_only=True):
        sudo("stop codalab-compute-worker")
        sudo("stop codalab-monitor")
        sudo("start codalab-compute-worker")
        sudo("start codalab-monitor")


@task
def setup_compute_worker_user():
    # Steps to setup compute worker:
    #   1) setup_compute_worker_user (only run this once as it creates a user and will probably fail if re-run)
    #   2) setup_compute_worker_permissions
    #   3) setup_compute_worker_and_monitoring
    sudo('adduser --quiet --disabled-password --gecos "" workeruser')
    sudo('echo workeruser:password | chpasswd')


@task
def setup_compute_worker_permissions():
    # Make the /codalabtemp/ files readable
    sudo("apt-get install bindfs")
    sudo("bindfs -o perms=0777 /codalabtemp /codalabtemp")

    # Make private stuff private
    sudo("chown -R azureuser:azureuser ~/codalab")
    sudo("chmod -R 700 ~/codalab")
    sudo("chown azureuser:azureuser ~/.codalabconfig")
    sudo("chmod 700 ~/.codalabconfig")


def setup_env():
    env.SHELL_ENV = dict(
        DJANGO_SETTINGS_MODULE=env.django_settings_module,
        DJANGO_CONFIGURATION=env.django_configuration,
        CONFIG_HTTP_PORT=env.config_http_port,
        CONFIG_SERVER_NAME=env.config_server_name,
    )
    return prefix('source /usr/local/bin/virtualenvwrapper.sh && workon venv'), shell_env(**env.SHELL_ENV)
