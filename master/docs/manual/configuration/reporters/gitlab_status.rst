.. bb:reporter:: GitLabStatusPush

GitLabStatusPush
++++++++++++++++

.. py:currentmodule:: buildbot.reporters.gitlab

.. code-block:: python

    from buildbot.plugins import reporters

    gl = reporters.GitLabStatusPush('private-token', context='continuous-integration/buildbot',
                                    baseURL='https://git.yourcompany.com')
    c['services'].append(gl)

:class:`GitLabStatusPush` publishes build status using `GitLab Commit Status API <http://doc.gitlab.com/ce/api/commits.html#commit-status>`_.
The build status is published to a specific commit SHA in GitLab.

It requires `txrequests`_ package to allow interaction with GitLab Commit Status API.

It uses private token auth, and the token owner is required to have at least developer access to each repository. As a result, we recommend you use https in your base_url rather than http.


.. py:class:: GitLabStatusPush(token, startDescription=None, endDescription=None, context=None, baseURL=None, verbose=False)

    :param string token: Private token of user permitted to update status for commits. (can be a :ref:`Secret`)
    :param string startDescription: Description used when build starts
    :param string endDescription: Description used when build ends
    :param string context: Name of your build system, eg. continuous-integration/buildbot
    :param string baseURL: the base url of the GitLab host, up to and optionally including the first `/` of the path. Do not include /api/
    :param string verbose: Be more verbose
    :param boolean verify: disable ssl verification for the case you use temporary self signed certificates
    :param boolean debug: logs every requests and their response

    .. _txrequests: https://pypi.python.org/pypi/txrequests
