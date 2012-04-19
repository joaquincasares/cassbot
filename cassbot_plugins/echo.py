from cassbot import BaseBotPlugin, natural_list
from twisted.internet import defer
from twisted.python import log

class Echo(BaseBotPlugin):
    def __init__(self):
        pass

    @defer.inlineCallbacks
    def respond(self, msg, outputcb):
        return msg

    def privmsg(self, bot, user, channel, msg):
        return msg
