from django.conf.urls import patterns, include, url
from django.views.generic import TemplateView

from .. import views

urlpatterns = patterns(
    '',
    url(r'^$', views.competition_index, name='list'),
    url(r'^(?P<pk>\d+)$', views.CompetitionDetailView.as_view(), name='view'),
    url(r'^create$', views.CompetitionUpload.as_view(), name='create'),
    url(r'^edit_competition/(?P<pk>\d+)$', views.CompetitionEdit.as_view(), name='edit'),
    url(r'^delete_competition/(?P<pk>\d+)$', views.CompetitionDelete.as_view(), name='delete'),
    url(r'^(?P<id>\d+)/submissions/(?P<phase>\d+)$', views.CompetitionSubmissionsPage.as_view(), name='competition_submissions_page'),
    url(r'^(?P<competition_id>\d+)/submission_metadata/(?P<phase_id>\d+)$', views.competition_submission_metadata_page, name='competition_submissions_metadata'),
    url(r'^(?P<id>\d+)/results/(?P<phase>\d+)$', views.CompetitionResultsPage.as_view(), name='competition_results_page'),
    url(r'^competition/submission/(?P<submission_id>\d+)/(?P<filetype>detailed_results.html)$',
        views.MyCompetitionSubmissionOutput.as_view(),
        name='my_competition_output'),
    url(r'^(?P<id>\d+)/results/(?P<phase>\d+)/data$', views.CompetitionResultsDownload.as_view(), name='competition_results_download'),
    url(r'^(?P<id>\d+)/results_complete/(?P<phase>\d+)/data$', views.CompetitionCompleteResultsDownload.as_view(), name='competition_results_complete_download'),
    url(r'^check_phase_migrations', views.CompetitionCheckMigrations.as_view(), name="competition_check_phase_migrations"),
    url(r'^message_participants/(?P<competition_id>\d+)', views.competition_message_participants, name="competition_message_participants"),
    url(r'^submission_delete/(?P<pk>\d+)', views.SubmissionDelete.as_view(), name="submission_delete"),
    url(r'^download_yaml/(?P<competition_pk>\d+)', views.download_competition_yaml, name="download_yaml"),
    url(r'^download/(?P<competition_pk>\d+)', views.download_competition_bundle, name="download"),
    url(r'^download_leaderboard_results/(?P<competition_pk>\d+)/(?P<phase_pk>\d+)', views.download_leaderboard_results, name="download_leaderboard_results"),
    url(r'^update_description/(?P<submission_pk>\d+)', views.submission_update_description, name="submission_update_description"),
    url(r'^mark_as_failed/(?P<submission_pk>\d+)', views.submission_mark_as_failed, name="submission_mark_as_failed"),
    url(r'^toggle_leaderboard/(?P<submission_pk>\d+)', views.submission_toggle_leaderboard, name="submission_toggle_leaderboard"),
    url(r'^submission_re_run/(?P<submission_pk>\d+)', views.submission_re_run, name="submission_re_run"),
)
