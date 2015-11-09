from rest_framework import routers
from . import views
from django.conf.urls import patterns, url
router = routers.DefaultRouter()

router.register(r'competition/(?P<competition_id>\d+)/participants', views.CompetitionParticipantAPIViewSet)
router.register(r'competition', views.CompetitionAPIViewSet)
router.register(r'competition/(?P<competition_id>\d+)/leaderboards', views.LeaderBoardViewSet)
router.register(r'defaultcontent', views.DefaultContentViewSet)

urlpatterns = router.urls

urlpatterns += (
    ### Competitions
    url(r'^competition/create$', views.CompetitionCreationApi.as_view(), name='api_competition_creation'),
    url(r'^competition/create/sas$', views.CompetitionCreationSasApi.as_view(), name='api_competition_creation_sas'),
    url(r'^competition/create/(?P<token>\d+)$', views.CompetitionCreationStatusApi.as_view(), name='api_competition_creation_status'),

    url(r'^competition/(?P<competition_id>\d+)/submission$',views.competition_submission_create,name='api_competition_submission_post'),
    url(r'^competition/(?P<competition_id>\d+)/submission/sas$',views.CompetitionSubmissionSasApi.as_view(), name='api_competition_submission_sas'),
    url(r'^competition/(?P<competition_id>\d+)/submission/(?P<pk>\d+)$',views.competition_submission_retrieve,name='api_competition_submission_get'),
    url(r'^competition/(?P<competition_id>\d+)/submission/(?P<pk>\d+)/leaderboard$',views.competition_submission_leaderboard,name='api_competition_submission_leaderboard'),

    url(r'^competition/(?P<pk>\d+)/phases/(?P<phasenumber>\d+)$',views.competitionphase_retrieve,name='api_competitionphase'),
    url(r'^competition/(?P<competition_id>\d+)/phases/(?P<phase_id>\d+)/leaderboard$',views.leaderboard_retrieve, name='api_phase_leaderboard'),
    url(r'^competition/(?P<competition_id>\d+)/phases/(?P<phase_id>\d+)/leaderboard/data$',views.LeaderBoardDataViewSet.as_view(), name='api_phase_leaderboarddata'),

    url(r'^competition/(?P<pk>\d+)/phases/$',views.competitionphase_list,name='api_competitionphases_list'),

    url(r'^competition/(?P<competition_id>\d+)/pages/(?P<category>[a-zA-Z][\w\d\-\_]*)/$', views.competition_page_list, name='api_competition_page_list'),
    url(r'^competition/(?P<competition_id>\d+)/pages/(?P<pk>\d+)$', views.competition_page, name='api_competition_page'),
    url(r'^competition/(?P<competition_id>\d+)/pages/$', views.competition_page_list, name='api_competition_page_list'),
    url(r'^competition/(?P<pk>\d+)/pages/(?P<entity_label>\w[\w\d\-\_]+)/$', views.competition_page_list, name='api_competition_page_list'),

    ### Worksheets
    url(r'^worksheets/$', views.WorksheetsListApi.as_view(), name='api_worksheets'),
    url(r'^worksheets/add/$', views.WorksheetsAddApi.as_view(), name='api_worksheets_add'),
    url(r'^worksheets/delete/$', views.WorksheetsDeleteApi.as_view(), name='api_worksheets_delete'),
    url(r'^worksheets/search/$', views.WorksheetsSearchApi.as_view(), name='api_worksheet_search'),
    url(r'^worksheets/get_uuid/$', views.WorksheetsGetUUIDApi.as_view(), name='api_worksheet_get_uuid'),
    url(r'^worksheets/bundle_list/$', views.WorksheetsGetBundleListApi.as_view(), name='api_worksheet_bundle_list'),
    url(r'^worksheets/command/$', views.WorksheetsCommandApi.as_view(), name='api_worksheets_command'),
    url(r'^worksheets/(?P<uuid>[A-Za-z0-9]+)/$', views.WorksheetContentApi.as_view(), name='api_worksheet_content'),

    url(r'^bundles/content/(?P<uuid>[A-Za-z0-9]+)/$', views.BundleContentApi.as_view(), name='api_bundle_content'),
    url(r'^bundles/content/(?P<uuid>[A-Za-z0-9]+)/(?P<path>\S*)/$', views.BundleContentApi.as_view(), name='api_bundle_content'),
    url(r'^bundles/filecontent/(?P<uuid>[A-Za-z0-9]+)/(?P<path>\S*)/$', views.BundleFileContentApi.as_view(), name='api_bundle_filecontent'),
    url(r'^bundles/search/$', views.BundleSearchApi.as_view(), name='api_bundle_search'),
    url(r'^bundles/get_uuid/$', views.BundleGetUUIDApi.as_view(), name='api_bundle_get_uuid'),
    url(r'^bundles/upload/$', views.BundleUploadApi.as_view(), name='api_bundle_upload'),
    url(r'^bundles/(?P<uuid>[A-Za-z0-9]+)/$', views.BundleInfoApi.as_view(), name='api_bundle_info'),
)
