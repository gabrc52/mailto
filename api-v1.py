#!/usr/bin/env python2
#
# Webathena-Moira Post Office Box interface, a mostly-RESTful API.
#
# Background:
#
# All actions are authenticated. Every request must include a cookie (in this
# case, named "mailto-session") containing the JSON-encoded value of the
# "session" attribute returned by Webathena. Inside of this credential should
# reside a Moira ticket (moira/moira7.mit.edu@ATHENA.MIT.EDU).
#
# Endpoints:
#
# GET /<user>
# List <user>'s post office boxes, including both current ones and disabled ones
# that we can find out about. Return the pobox status as a dictionary:
#  - boxes: a list of dictionaries, each containing:
#     - address: the pobox represented as an email address
#     - type: the type of box, either "IMAP", "EXCHANGE" or "SMTP"
#     - enabled: a boolean value, true iff mail is being sent to this pobox
#  - modtime: the time of the last modification, in ISO 8601 format
#  - modby: the username of the person who performed the modification
#  - modwith: the tool used to modify the settings
#
# PUT /<user>/<address>
# Set <address> as <user>'s only post office box. Return the updated list of
# poboxes in the same format as the GET call.
#
# PUT /<user>/<internal>/<external>
# Set <internal> as <user>'s internal post office box and <external> as the
# external forwarder. The internal pobox must be of type IMAP or EXCHANGE, and
# the external pobox must be of type SMTP. Return the updated list of poboxes in
# the same format as the GET call.
#
# PUT /<user>/reset
# Reset <user>'s post office box settings using the set_pobox_pop query. Return
# the updated list of poboxes in the same format as the GET call.
#

import os
import re

from bottle import get, put, delete, abort, request
from bottle_webathena import *
from datetime import datetime

APP_ROOT = os.path.abspath(os.path.dirname(__file__))


@get("/<user>")
@proxied_moira
@json_api
def get_poboxes(moira_query, user):
    return pobox_status(moira_query, user)

@put("/<user>/reset")
@proxied_moira
@json_api
def reset(moira_query, user):
    moira_query("set_pobox_pop", user)
    return pobox_status(moira_query, user)

@put("/<user>/<address>")
@proxied_moira
@json_api
def put_address(moira_query, user, address):
    mtype, box = type_and_box(address)
    moira_query("set_pobox", user, mtype, box)
    return pobox_status(moira_query, user)

@put("/<user>/<internal>/<external>")
@proxied_moira
@json_api
def put_split_addresses(moira_query, user, internal, external):
    internal_mtype, internal_box = type_and_box(internal)
    if internal_mtype == "SMTP":
        abort(400, "Internal address cannot be type SMTP.")
    external_mtype, external_box = type_and_box(external)
    if external_mtype != "SMTP":
        abort(400, "External address must be type SMTP.")
    moira_query("set_pobox", user, internal_mtype, internal_box)
    moira_query("set_pobox", user, "SPLIT", external_box)
    return pobox_status(moira_query, user)


def pobox_status(moira_query, user):
    # Run Moira Query
    try:
        boxinfo = moira_query("get_pobox", user)[0]
    except moira.MoiraException as e:
        if len(e.args) >= 2 and e[1].lower() == "no such user":
            abort(404, e[1])
        raise e

    # Search Moira
    moira_addresses = boxinfo["address"].split(", ")
    exchange = []
    imap = []
    external = []
    for address in moira_addresses:
        # Categorize as Exchange, IMAP or External
        if re.search("@EXCHANGE.MIT.EDU$", address, re.IGNORECASE):
            exchange.append(address)
        elif re.search("@PO\d+.MIT.EDU$", address, re.IGNORECASE):
            imap.append(address)
        else:
            external.append(address)

    # Construct Response
    boxes = []
    for addresses, mtype in ((exchange, "EXCHANGE"), (imap, "IMAP"),
        (external, "SMTP")):
        for address in addresses:
            boxes.append({"address": address,
                          "type": mtype,
                          "enabled": True})
    isotime = datetime.strptime(boxinfo["modtime"], MOIRA_TIME_FORMAT) \
        .isoformat()
    return {"boxes": boxes,
            "modtime": isotime,
            "modwith": boxinfo["modwith"],
            "modby": boxinfo["modby"]}

def type_and_box(address):
    """Return the type and box associated with an email address."""
    if re.search("@EXCHANGE.MIT.EDU$", address, re.IGNORECASE):
        return "EXCHANGE", "EXCHANGE.MIT.EDU"
    elif re.search("@PO\d+.MIT.EDU$", address, re.IGNORECASE):
        username = address.split("@")[0]
        return "IMAP", "%s.po" % username
    else:
        return "SMTP", address


if __name__ == "__main__":
    import bottle
    from flup.server.fcgi import WSGIServer
    bottle.debug(True) # TODO: disable this
    app = bottle.default_app()
    WSGIServer(app).run()
