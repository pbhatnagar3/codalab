import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.views.generic import DetailView, CreateView

from apps.web.models import Competition
from apps.web.views import LoginRequiredMixin
from .forms import PostForm, ThreadForm
from .models import Forum, Thread, Post


User = get_user_model()


class ForumBaseMixin(object):

    def dispatch(self, *args, **kwargs):
        # Get object early so we can access it in multiple places
        self.forum = get_object_or_404(Forum, pk=self.kwargs['forum_pk'])
        if 'thread_pk' in self.kwargs:
            self.thread = get_object_or_404(Thread, pk=self.kwargs['thread_pk'])
        return super(ForumBaseMixin, self).dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(ForumBaseMixin, self).get_context_data(**kwargs)
        context['forum'] = self.forum
        context['thread'] = self.thread if hasattr(self, 'thread') else None
        return context


class ForumDetailView(DetailView, ForumBaseMixin):
    model = Forum
    template_name = "forums/thread_list.html"
    pk_url_kwarg = 'forum_pk'


class RedirectToThreadMixin(object):

    def get_success_url(self):
        return self.thread.get_absolute_url()


class CreatePostView(ForumBaseMixin, RedirectToThreadMixin, LoginRequiredMixin, CreateView):
    model = Post
    template_name = "forums/post_form.html"
    form_class = PostForm

    def form_valid(self, form):
        self.post = form.save(commit=False)
        self.post.thread = self.thread
        self.post.posted_by = self.request.user
        self.post.save()

        self.thread.last_post_date = datetime.datetime.now()
        self.thread.save()
        self.thread.notify_all_posters_of_new_post()
        return HttpResponseRedirect(self.get_success_url())


class CreateThreadView(ForumBaseMixin, RedirectToThreadMixin, LoginRequiredMixin, CreateView):
    model = Thread
    template_name = "forums/post_form.html"
    form_class = ThreadForm

    def form_valid(self, form):
        self.thread = form.save(commit=False)
        self.thread.forum = self.forum
        self.thread.started_by = self.request.user
        self.thread.last_post_date = datetime.datetime.now()
        self.thread.save()

        # Make first post in the thread with the content
        Post.objects.create(thread=self.thread,
                            content=form.cleaned_data['content'],
                            posted_by=self.request.user)

        return HttpResponseRedirect(self.get_success_url())


class ThreadDetailView(ForumBaseMixin, DetailView):
    model = Thread
    template_name = "forums/thread_detail.html"
    pk_url_kwarg = 'thread_pk'

