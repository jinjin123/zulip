from __future__ import absolute_import

from typing import Iterable, List, Text, Tuple

from django.http import HttpRequest, HttpResponse
from django.utils.translation import ugettext as _

from zerver.lib.request import JsonableError
from zerver.models import UserProfile, Stream, Subscription, \
    Recipient, bulk_get_recipients, get_recipient, get_stream

def access_stream_common(user_profile, stream, error):
    # type: (UserProfile, Stream, Text) -> Tuple[Recipient, Subscription]
    """Common function for backend code where the target use attempts to
    access the target stream, returning all the data fetched along the
    way.  If that user does not have permission to access that stream,
    we throw an exception.  A design goal is that the error message is
    the same for streams you can't access and streams that don't exist."""

    # First, we don't allow any access to streams in other realms.
    if stream.realm_id != user_profile.realm_id:
        raise JsonableError(error)

    recipient = get_recipient(Recipient.STREAM, stream.id)

    try:
        sub = Subscription.objects.get(user_profile=user_profile,
                                       recipient=recipient,
                                       active=True)
    except Subscription.DoesNotExist:
        sub = None

    # If the stream is in your realm and public, you can access it.
    if stream.is_public():
        return (recipient, sub)

    # Or if you are subscribed to the stream, you can access it.
    if sub is not None:
        return (recipient, sub)

    # Otherwise it is a private stream and you're not on it, so throw
    # an error.
    raise JsonableError(error)

def access_stream_by_id(user_profile, stream_id):
    # type: (UserProfile, int) -> Tuple[Stream, Recipient, Subscription]
    error = _("Invalid stream id")
    try:
        stream = Stream.objects.get(id=stream_id)
    except Stream.DoesNotExist:
        raise JsonableError(error)

    (recipient, sub) = access_stream_common(user_profile, stream, error)
    return (stream, recipient, sub)

def access_stream_by_name(user_profile, stream_name):
    # type: (UserProfile, Text) -> Tuple[Stream, Recipient, Subscription]
    error = _("Invalid stream name '%s'" % (stream_name,))
    stream = get_stream(stream_name, user_profile.realm)
    if stream is None:
        raise JsonableError(error)

    (recipient, sub) = access_stream_common(user_profile, stream, error)
    return (stream, recipient, sub)

def filter_stream_authorization(user_profile, streams):
    # type: (UserProfile, Iterable[Stream]) -> Tuple[List[Stream], List[Stream]]
    streams_subscribed = set() # type: Set[int]
    recipients_map = bulk_get_recipients(Recipient.STREAM, [stream.id for stream in streams])
    subs = Subscription.objects.filter(user_profile=user_profile,
                                       recipient__in=list(recipients_map.values()),
                                       active=True)

    for sub in subs:
        streams_subscribed.add(sub.recipient.type_id)

    unauthorized_streams = [] # type: List[Stream]
    for stream in streams:
        # The user is authorized for his own streams
        if stream.id in streams_subscribed:
            continue

        # The user is not authorized for invite_only streams
        if stream.invite_only:
            unauthorized_streams.append(stream)

    authorized_streams = [stream for stream in streams if
                          stream.id not in set(stream.id for stream in unauthorized_streams)]
    return authorized_streams, unauthorized_streams