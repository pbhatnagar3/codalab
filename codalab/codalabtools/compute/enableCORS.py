# Add codalabtools to the module search path
import sys
import yaml
from os.path import dirname, abspath
sys.path.append(dirname(dirname(dirname(abspath(__file__)))))
from codalabtools.azure_extensions import (
    Cors, CorsRule, set_storage_service_cors_properties)

account_name = raw_input("Enter azure account name:")
account_key = raw_input("Enter azurre key:")
cors_rule = CorsRule()
cors_rule.allowed_origins = '*'  # this is fine for dev setup
cors_rule.allowed_methods = 'PUT'
cors_rule.exposed_headers = '*'
cors_rule.allowed_headers = '*'
cors_rule.max_age_in_seconds = 1800
cors_rules = Cors()
cors_rules.cors_rule.append(cors_rule)
set_storage_service_cors_properties(account_name, account_key, cors_rules)
