"""
Defines background tasks needed by the web site.
"""
import csv
import io
import json
import logging
import StringIO
import zipfile

from urllib import pathname2url
from zipfile import ZipFile
from django.conf import settings
from django.contrib.sites.models import get_current_site
from django.core.files.base import ContentFile
from django.core.mail import get_connection, EmailMultiAlternatives, send_mail
from django.db import transaction
from django.db.models import Count
from django.template import Context
from django.template.loader import render_to_string
from django.contrib.sites.models import Site
from apps.jobs.models import (Job,
                              run_job_task,
                              JobTaskResult,
                              getQueue)
from apps.web.models import (add_submission_to_leaderboard,
                             Competition,
                             CompetitionSubmission,
                             CompetitionDefBundle,
                             CompetitionSubmissionStatus,
                             submission_prediction_output_filename,
                             submission_output_filename,
                             submission_detailed_results_filename,
                             submission_private_output_filename,
                             submission_stdout_filename,
                             submission_stderr_filename,
                             submission_history_file_name,
                             submission_scores_file_name,
                             submission_coopetition_file_name,
                             predict_submission_stdout_filename,
                             predict_submission_stderr_filename,
                             SubmissionScore,
                             SubmissionScoreDef,
                             CompetitionSubmissionMetadata)
from apps.coopetitions.models import DownloadRecord

logger = logging.getLogger(__name__)


# Echo
def echo_task(job_id, args):
    """
    A simple task to echo a message provided as args['message']. The associated job will
    be marked as Finished if the message is echoes successfully. Otherwise the job will be
    marked as Failed.

    job_id: The ID of the job.
    args: A dictionary with the arguments for the task. Expected items are:
        args['message']: string to send as info to the module's logger.
    """
    def echo_it(job):
        """Echoes the message specified."""
        logger.info("Echoing (job id=%s): %s", job.id, args['message'])
        return JobTaskResult(status=Job.FINISHED)

    run_job_task(job_id, echo_it)

def echo(text):
    """
    Echoes the text specified. This is for testing.

    text: The text to echo.

    Returns a Job object which can be used to track the progress of the operation.
    """
    return Job.objects.create_and_dispatch_job('echo', {'message': text})

# Create competition

def create_competition_task(job_id, args):
    """
    A task to create a competition from a bundle with the competition's definition.

    job_id: The ID of the job.
    args: A dictionary with the arguments for the task. Expected items are:
        args['comp_def_id']: The ID of the bundle holding the competition definition.
    Once the task succeeds, a new competition will be ready to use in CodaLab.
    """
    def create_it(job):
        """Handles the actual creation of the competition"""
        comp_def_id = args['comp_def_id']
        logger.info("Creating competition for competition bundle (bundle_id=%s, job_id=%s)",
                    comp_def_id, job.id)
        competition_def = CompetitionDefBundle.objects.get(pk=comp_def_id)
        competition = competition_def.unpack()
        logger.info("Created competition for competition bundle (bundle_id=%s, job_id=%s, comp_id=%s)",
                    comp_def_id, job.id, competition.pk)
        return JobTaskResult(status=Job.FINISHED, info={'competition_id': competition.pk})

    run_job_task(job_id, create_it)

def create_competition(comp_def_id):
    """
    Starts the process of creating a competition given a bundle with the competition's definition.

    comp_def_id: The ID of the bundle holding the competition definition.
                 See: https://github.com/codalab/codalab/wiki/12.-Building-a-Competition-Bundle.

    Returns a Job object which can be used to track the progress of the operation.
    """
    return Job.objects.create_and_dispatch_job('create_competition', {'comp_def_id': comp_def_id})

# Evaluate submissions in a competition

# CompetitionSubmission states which are final.
_FINAL_STATES = {
    CompetitionSubmissionStatus.FINISHED,
    CompetitionSubmissionStatus.FAILED,
    CompetitionSubmissionStatus.CANCELLED
}

def _set_submission_status(submission_id, status_codename):
    """
    Update the status of a submission.

    submission_id: PK of CompetitionSubmission object.
    status_codename: New status codename.
    """
    status = CompetitionSubmissionStatus.objects.get(codename=status_codename)
    with transaction.commit_on_success():
        submission = CompetitionSubmission.objects.select_for_update().get(pk=submission_id)
        old_status_codename = submission.status.codename
        if old_status_codename not in _FINAL_STATES:
            submission.status = status
            submission.save()
            logger.info("Changed submission status from %s to %s (id=%s).",
                        old_status_codename, status_codename, submission_id)
        else:
            logger.info("Skipping update of submission status: invalid transition %s -> %s  (id=%s).",
                        status_codename, old_status_codename, submission_id)

def predict(submission, job_id):
    """
    Dispatches the prediction taks for the given submission to an appropriate compute worker.

    submission: The CompetitionSubmission object.
    job_id: The job ID used to track the progress of the evaluation.
    """
    # Generate metadata-only bundle describing the computation
    lines = []
    program_value = submission.file.name

    if len(program_value) > 0:
        lines.append("program: %s" % program_value)
    else:
        raise ValueError("Program is missing.")
    input_value = submission.phase.input_data.name

    logger.info("Running prediction")

    if len(input_value) > 0:
        lines.append("input: %s" % input_value)
    lines.append("stdout: %s" % submission_stdout_filename(submission))
    lines.append("stderr: %s" % submission_stderr_filename(submission))
    submission.prediction_runfile.save('run.txt', ContentFile('\n'.join(lines)))
    # Create stdout.txt & stderr.txt
    username = submission.participant.user.username
    lines = ["Standard output for submission #{0} by {1}.".format(submission.submission_number, username), ""]
    submission.stdout_file.save('stdout.txt', ContentFile('\n'.join(lines)))
    submission.prediction_stdout_file.save('prediction_stdout_file.txt', ContentFile('\n'.join(lines)))
    lines = ["Standard error for submission #{0} by {1}.".format(submission.submission_number, username), ""]
    submission.stderr_file.save('stderr.txt', ContentFile('\n'.join(lines)))
    submission.prediction_stderr_file.save('prediction_stderr_file.txt', ContentFile('\n'.join(lines)))

    # Store workflow state
    submission.execution_key = json.dumps({'predict' : job_id})
    submission.save()
    # Submit the request to the computation service
    body = json.dumps({
        "id" : job_id,
        "task_type": "run",
        "task_args": {
            "bundle_id": submission.prediction_runfile.name,
            "container_name": settings.BUNDLE_AZURE_CONTAINER,
            "reply_to": settings.SBS_RESPONSE_QUEUE,
            "execution_time_limit": submission.phase.execution_time_limit,
            "predict": True,
        }
    })

    getQueue(settings.SBS_COMPUTE_QUEUE).send_message(body)
    # Update the submission object
    _set_submission_status(submission.id, CompetitionSubmissionStatus.SUBMITTED)

def score(submission, job_id):
    """
    Dispatches the scoring task for the given submission to an appropriate compute worker.

    submission: The CompetitionSubmission object.
    job_id: The job ID used to track the progress of the evaluation.
    """
    # Loads the computation state.
    state = {}
    if len(submission.execution_key) > 0:
        state = json.loads(submission.execution_key)
    has_generated_predictions = 'predict' in state

    #generate metadata-only bundle describing the history of submissions and phases
    last_submissions = CompetitionSubmission.objects.filter(
        participant=submission.participant,
        status__codename=CompetitionSubmissionStatus.FINISHED
    ).order_by('-submitted_at')


    lines = []
    lines.append("description: history of all previous successful runs output files")

    if last_submissions:
        for past_submission in last_submissions:
            if past_submission.pk != submission.pk:
                #pad folder numbers for sorting os side, 001, 002, 003,... 010, etc...
                past_submission_phasenumber = '%03d' % past_submission.phase.phasenumber
                past_submission_number = '%03d' % past_submission.submission_number
                lines.append('%s/%s/output/: %s' % (
                        past_submission_phasenumber,
                        past_submission_number,
                        submission_private_output_filename(past_submission),
                    )
                )
    else:
        pass

    submission.history_file.save('history.txt', ContentFile('\n'.join(lines)))

    score_csv = submission.phase.competition.get_results_csv(submission.phase.pk)
    submission.scores_file.save('scores.txt', ContentFile(score_csv))

    # Extra submission info
    coopetition_zip_buffer = StringIO.StringIO()
    coopetition_zip_file = zipfile.ZipFile(coopetition_zip_buffer, "w")

    for phase in submission.phase.competition.phases.all():
        coopetition_field_names = (
            "participant__user__username",
            "pk",
            "when_made_public",
            "when_unmade_public",
            "started_at",
            "completed_at",
            "download_count",
            "submission_number",
        )
        annotated_submissions = phase.submissions.filter(status__codename=CompetitionSubmissionStatus.FINISHED).values(
            *coopetition_field_names
        ).annotate(like_count=Count("likes"), dislike_count=Count("dislikes"))

        # Add this after fetching annotated count from db
        coopetition_field_names += ("like_count", "dislike_count")

        coopetition_csv = StringIO.StringIO()
        writer = csv.DictWriter(coopetition_csv, coopetition_field_names)
        writer.writeheader()
        for row in annotated_submissions:
            writer.writerow(row)

        coopetition_zip_file.writestr('coopetition_phase_%s.txt' % phase.phasenumber, coopetition_csv.getvalue().encode('utf-8'))

    # Scores metadata
    for phase in submission.phase.competition.phases.all():
        coopetition_zip_file.writestr(
            'coopetition_scores_phase_%s.txt' % phase.phasenumber,
            phase.competition.get_results_csv(phase.pk, include_scores_not_on_leaderboard=True).encode('utf-8')
        )

    # Download metadata
    coopetition_downloads_csv = StringIO.StringIO()
    writer = csv.writer(coopetition_downloads_csv)
    writer.writerow((
        "submission_pk",
        "submission_owner",
        "downloaded_by",
        "time_of_download",
    ))
    for download in DownloadRecord.objects.filter(submission__phase__competition=submission.phase.competition):
        writer.writerow((
            download.submission.pk,
            download.submission.participant.user.username,
            download.user.username,
            str(download.timestamp),
        ))

    coopetition_zip_file.writestr('coopetition_downloads.txt', coopetition_downloads_csv.getvalue().encode('utf-8'))

    # Current user
    coopetition_zip_file.writestr('current_user.txt', submission.participant.user.username.encode('utf-8'))
    coopetition_zip_file.close()

    # Save them all
    submission.coopetition_file.save('coopetition.zip', ContentFile(coopetition_zip_buffer.getvalue()))

    # Generate metadata-only bundle describing the inputs. Reference data is an optional
    # dataset provided by the competition organizer. Results are provided by the participant
    # either indirectly (has_generated_predictions is True i.e. participant provides a program
    # which is run to generate results) ordirectly (participant uploads results directly).
    lines = []
    ref_value = submission.phase.reference_data.name
    if len(ref_value) > 0:
        lines.append("ref: %s" % ref_value)
    res_value = submission.prediction_output_file.name if has_generated_predictions else submission.file.name
    if len(res_value) > 0:
        lines.append("res: %s" % res_value)
    else:
        raise ValueError("Results are missing.")

    lines.append("history: %s" % submission_history_file_name(submission))
    lines.append("scores: %s" % submission_scores_file_name(submission))
    lines.append("coopetition: %s" % submission_coopetition_file_name(submission))
    lines.append("submitted-by: %s" % submission.participant.user.username)
    lines.append("submitted-at: %s" % submission.submitted_at.replace(microsecond=0).isoformat())
    lines.append("competition-submission: %s" % submission.submission_number)
    lines.append("competition-phase: %s" % submission.phase.phasenumber)
    is_automatic_submission = False
    if submission.phase.auto_migration:
        # If this phase has auto_migration and this submission is the first in the phase, it is an automatic submission!
        submissions_this_phase = CompetitionSubmission.objects.filter(
            phase=submission.phase,
            participant=submission.participant
        ).count()
        is_automatic_submission = submissions_this_phase == 1

    lines.append("automatic-submission: %s" % is_automatic_submission)
    submission.inputfile.save('input.txt', ContentFile('\n'.join(lines)))


    # Generate metadata-only bundle describing the computation.
    lines = []
    program_value = submission.phase.scoring_program.name
    if len(program_value) > 0:
        lines.append("program: %s" % program_value)
    else:
        raise ValueError("Program is missing.")
    lines.append("input: %s" % submission.inputfile.name)
    lines.append("stdout: %s" % submission_stdout_filename(submission))
    lines.append("stderr: %s" % submission_stderr_filename(submission))
    submission.runfile.save('run.txt', ContentFile('\n'.join(lines)))

    # Create stdout.txt & stderr.txt
    if has_generated_predictions == False:
        username = submission.participant.user.username
        lines = ["Standard output for submission #{0} by {1}.".format(submission.submission_number, username), ""]
        submission.stdout_file.save('stdout.txt', ContentFile('\n'.join(lines)))
        lines = ["Standard error for submission #{0} by {1}.".format(submission.submission_number, username), ""]
        submission.stderr_file.save('stderr.txt', ContentFile('\n'.join(lines)))
    # Update workflow state
    state['score'] = job_id
    submission.execution_key = json.dumps(state)
    submission.save()
    # Submit the request to the computation service
    body = json.dumps({
        "id" : job_id,
        "task_type": "run",
        "task_args": {
            "bundle_id" : submission.runfile.name,
            "container_name" : settings.BUNDLE_AZURE_CONTAINER,
            "reply_to" : settings.SBS_RESPONSE_QUEUE,
            "execution_time_limit": submission.phase.execution_time_limit,
            "predict": False,
        }
    })
    getQueue(settings.SBS_COMPUTE_QUEUE).send_message(body)
    if has_generated_predictions == False:
        _set_submission_status(submission.id, CompetitionSubmissionStatus.SUBMITTED)

class SubmissionUpdateException(Exception):
    """Defines an exception that occurs during the update of a CompetitionSubmission object."""
    def __init__(self, submission, inner_exception):
        super(SubmissionUpdateException, self).__init__(inner_exception.message)
        self.submission = submission
        self.inner_exception = inner_exception

def update_submission_task(job_id, args):
    """
    A task to update the status of a submission in a competition.

    job_id: The ID of the job.
    args: A dictionary with the arguments for the task. Expected items are:
        args['status']: The evaluation status, which is one of 'running', 'finished' or 'failed'.
    """

    def update_submission(submission, status, job_id, traceback=None, metadata=None):
        """
        Updates the status of a submission.

        submission: The CompetitionSubmission object to update.
        status: The new status string: 'running', 'finished' or 'failed'.
        job_id: The job ID used to track the progress of the evaluation.
        """
        state = {}
        if len(submission.execution_key) > 0:
            logger.debug("update_submission_task loading state: %s", submission.execution_key)
            state = json.loads(submission.execution_key)
            logger.debug("update_submission_task state = %s" % submission.execution_key)

        if metadata:
            is_predict = 'score' not in state
            sub_metadata, created = CompetitionSubmissionMetadata.objects.get_or_create(
                is_predict=is_predict,
                is_scoring=not is_predict,
                submission=submission,
            )
            sub_metadata.__dict__.update(metadata)
            sub_metadata.save()
            logger.debug("saving extra metadata, was a new object created? %s" % created)

        if status == 'running':
            _set_submission_status(submission.id, CompetitionSubmissionStatus.RUNNING)
            return Job.RUNNING

        if status == 'finished':
            result = Job.FAILED
            if 'score' in state:
                logger.debug("update_submission_task loading final scores (pk=%s)", submission.pk)
                submission.output_file.name = pathname2url(submission_output_filename(submission))
                submission.private_output_file.name = pathname2url(submission_private_output_filename(submission))
                submission.detailed_results_file.name = pathname2url(submission_detailed_results_filename(submission))
                submission.save()
                logger.debug("Retrieving output.zip and 'scores.txt' file (submission_id=%s)", submission.id)
                logger.debug("Output.zip location=%s" % submission.output_file.file.name)
                ozip = ZipFile(io.BytesIO(submission.output_file.read()))
                scores = None
                try:
                    scores = open(ozip.extract('scores.txt'), 'r').read()
                except Exception:
                    logger.error("Scores.txt not found, unable to process submission: %s (submission_id=%s)", status, submission.id)
                    _set_submission_status(submission.id, CompetitionSubmissionStatus.FAILED)
                    return Job.FAILED

                logger.debug("Processing scores... (submission_id=%s)", submission.id)
                for line in scores.split("\n"):
                    if len(line) > 0:
                        label, value = line.split(":")
                        logger.debug("Attempting to submit score %s:%s" % (label, value))
                        try:
                            scoredef = SubmissionScoreDef.objects.get(competition=submission.phase.competition,
                                                                      key=label.strip())
                            SubmissionScore.objects.create(result=submission, scoredef=scoredef, value=float(value))
                        except SubmissionScoreDef.DoesNotExist:
                            logger.warning("Score %s does not exist (submission_id=%s)", label, submission.id)
                logger.debug("Done processing scores... (submission_id=%s)", submission.id)
                _set_submission_status(submission.id, CompetitionSubmissionStatus.FINISHED)
                # Automatically submit to the leaderboard?
                if submission.phase.is_blind:
                    logger.debug("Adding to leaderboard... (submission_id=%s)", submission.id)
                    add_submission_to_leaderboard(submission)
                    logger.debug("Leaderboard updated with latest submission (submission_id=%s)", submission.id)

                if submission.phase.competition.force_submission_to_leaderboard:
                    add_submission_to_leaderboard(submission)
                    logger.debug("Force submission added submission to leaderboard (submission_id=%s)", submission.id)

                result = Job.FINISHED

                if submission.participant.user.email_on_submission_finished_successfully:
                    email = submission.participant.user.email
                    site_url = "https://%s%s" % (Site.objects.get_current().domain, submission.phase.competition.get_absolute_url())
                    send_mail(
                        'Submission has finished successfully!',
                        'Your submission to the competition "%s" has finished successfully! View it here: %s' %
                        (submission.phase.competition.title, site_url),
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        fail_silently=False
                    )
            else:
                logger.debug("update_submission_task entering scoring phase (pk=%s)", submission.pk)
                url_name = pathname2url(submission_prediction_output_filename(submission))
                submission.prediction_output_file.name = url_name
                submission.prediction_stderr_file.name = pathname2url(predict_submission_stdout_filename(submission))
                submission.prediction_stdout_file.name = pathname2url(predict_submission_stderr_filename(submission))
                submission.save()
                try:
                    score(submission, job_id)
                    result = Job.RUNNING
                    logger.debug("update_submission_task scoring phase entered (pk=%s)", submission.pk)
                except Exception:
                    logger.exception("update_submission_task failed to enter scoring phase (pk=%s)", submission.pk)
            return result

        if status != 'failed':
            logger.error("Invalid status: %s (submission_id=%s)", status, submission.id)

        if traceback:
            submission.exception_details = traceback
            submission.save()

        _set_submission_status(submission.id, CompetitionSubmissionStatus.FAILED)

    def handle_update_exception(job, ex):
        """
        Handles exception that occur while attempting to update the status of a submission.

        job: The running Job instance.
        ex: The exception. The handler tries to acquire the CompetitionSubmission instance
            from a submission attribute on the exception.
        """
        try:
            submission = ex.submission
            _set_submission_status(submission.id, CompetitionSubmissionStatus.FAILED)
        except Exception:
            logger.exception("Unable to set the submission status to Failed (job_id=%s)", job.id)
        return JobTaskResult(status=Job.FAILED)

    def update_it(job):
        """Updates the database to reflect the state of the evaluation of the given competition submission."""
        logger.debug("Entering update_submission_task::update_it (job_id=%s)", job.id)
        if job.task_type != 'evaluate_submission':
            raise ValueError("Job has incorrect task_type (job.task_type=%s)", job.task_type)
        task_args = job.get_task_args()
        submission_id = task_args['submission_id']
        logger.debug("Looking for submission (job_id=%s, submission_id=%s)", job.id, submission_id)
        submission = CompetitionSubmission.objects.get(pk=submission_id)
        status = args['status']
        logger.debug("Ready to update submission status (job_id=%s, submission_id=%s, status=%s)",
                     job.id, submission_id, status)
        result = None
        try:
            traceback = None
            metadata = None
            if 'extra' in args:
                if 'traceback' in args['extra']:
                    traceback = args['extra']['traceback']

                if 'metadata' in args['extra']:
                    metadata = args['extra']['metadata']

            result = update_submission(submission, status, job.id, traceback, metadata)
        except Exception as e:
            logger.exception("Failed to update submission (job_id=%s, submission_id=%s, status=%s)",
                             job.id, submission_id, status)
            raise SubmissionUpdateException(submission, e)
        return JobTaskResult(status=result)

    run_job_task(job_id, update_it, handle_update_exception)


def evaluate_submission_task(job_id, args):
    """
    A task to start the evaluation of a user's submission in a competition.

    job_id: The ID of the job.
    args: A dictionary with the arguments for the task. Expected items are:
        args['submission_id']: The ID of the CompetitionSubmission object.
        args['predict']: A boolean value set to True to cause the evaluation to
           generate predictions followed by a scoring round or set to False to
           limit the evaluation to a scoring round.
    """

    def submit_it():
        """Start the process to evaluate the given competition submission."""
        logger.debug("evaluate_submission_task begins (job_id=%s)", job_id)
        submission_id = args['submission_id']
        logger.debug("evaluate_submission_task submission_id=%s (job_id=%s)", submission_id, job_id)
        predict_and_score = args['predict'] == True
        logger.debug("evaluate_submission_task predict_and_score=%s (job_id=%s)", predict_and_score, job_id)
        submission = CompetitionSubmission.objects.get(pk=submission_id)

        task_name, task_func = ('prediction', predict) if predict_and_score else ('scoring', score)
        try:
            logger.debug("evaluate_submission_task dispatching %s task (submission_id=%s, job_id=%s)",
                        task_name, submission_id, job_id)
            task_func(submission, job_id)
            logger.debug("evaluate_submission_task dispatched %s task (submission_id=%s, job_id=%s)",
                        task_name, submission_id, job_id)
        except Exception:
            logger.exception("evaluate_submission_task dispatch failed (job_id=%s, submission_id=%s)",
                             job_id, submission_id)
            update_submission_task(job_id, {'status': 'failed'})
        logger.debug("evaluate_submission_task ends (job_id=%s)", job_id)

    submit_it()

def evaluate_submission(submission_id, is_scoring_only):
    """
    Starts the process of evaluating a user's submission to a competition.

    submission_id: The ID of the CompetitionSubmission object.
    is_scoring_only: True to skip the prediction step.

    Returns a Job object which can be used to track the progress of the operation.
    """
    task_args = {'submission_id': submission_id, 'predict': (not is_scoring_only)}
    return Job.objects.create_and_dispatch_job('evaluate_submission', task_args)


def _send_mass_html_mail(datatuple, fail_silently=False, user=None, password=None,
                        connection=None):
    connection = connection or get_connection(
        username=user, password=password, fail_silently=fail_silently
    )

    messages = []
    for subject, text, html, from_email, recipient in datatuple:
        message = EmailMultiAlternatives(subject, text, from_email, recipient)
        message.attach_alternative(html, 'text/html')
        messages.append(message)

    return connection.send_messages(messages)


def send_mass_email_task(job_id, task_args):
    competition = Competition.objects.get(pk=task_args["competition_pk"])
    body = task_args["body"]
    subject = task_args["subject"]
    from_email = task_args["from_email"]
    to_emails = task_args["to_emails"]

    context = Context({"competition": competition, "body": body, "site": Site.objects.get_current()})
    text = render_to_string("emails/notifications/participation_organizer_direct_email.txt", context)
    html = render_to_string("emails/notifications/participation_organizer_direct_email.html", context)

    mail_tuples = ((subject, text, html, from_email, [e]) for e in to_emails)

    _send_mass_html_mail(mail_tuples)


def send_mass_email(competition, body=None, subject=None, from_email=None, to_emails=None):
    task_args = {
        "competition_pk": competition.pk,
        "body": body,
        "subject": subject,
        "from_email": from_email,
        "to_emails": to_emails
    }
    return Job.objects.create_and_dispatch_job('send_mass_email', task_args)
