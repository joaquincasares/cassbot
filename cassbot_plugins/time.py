from twisted.internet import defer, error
from twisted.python import log
from twisted.web import soap, error as web_error
from cassbot import BaseBotPlugin, mask_matches, require_priv

from datetime import datetime

class TimeInstance:
    def __init__(self, longcode, shortcode=None):
        self.set_shortcode(shortcode)
        self.set_longcode(longcode)

    def __repr__(self):
        return '<%s %s %s [%s]>' % (self.__class__.__name__, self.longcode, self.shortcode)

    def set_longcode(self, longcode):
        self.longcode = longcode
        # self.longcode_re = re.compile(r'''(?:^|[[\s({<>:",@*'~])%s-(?P<command>\d+)\b''' % re.escape(longcode))

    def set_shortcode(self, shortcode):
        self.shortcode = shortcode
        self.shortcode_re = None
        if shortcode is not None:
            # self.shortcode_re = re.compile(r'''(?:^|[[\s({<>:",@*'~])%s(?P<command>\d+)\b''' % re.escape(shortcode))

    @classmethod
    def from_save_data(cls, savedata):
        return cls(savedata['longcode'], savedata['shortcode'])

    def to_save_data(self):
        return {'longcode': self.longcode, 'shortcode': self.shortcode}

    def find_short_code_references(self, message):
        return [tm.group('command') for tm in self.shortcode_re.finditer(message)]

    def find_long_code_references(self, message):
        return [tm.group('command') for tm in self.longcode_re.finditer(message)]

    def find_command_references(self, message):
        return self.find_short_code_references(message) + self.find_long_code_references(message)

    @defer.inlineCallbacks
    def find_date(self, command):
        time_value = ''
        if command.lower() == 'now':
            time_value = str(datetime.now())
        defer.returnValue(time_value)

    def reply_to_text(self, message, outputcb):
        commands = self.find_command_references(message)
        return defer.DeferredList([self.find_date(command).addCallback(outputcb) for command in commands])

class TimeIntegration(BaseBotPlugin):
    def __init__(self):
        BaseBotPlugin.__init__(self)
        self.time_instances = []

    def loadState(self, state):
        instance_data = state.get('time_instances', [])
        self.time_instances = map(TimeInstance.from_save_data, instance_data)

    def saveState(self):
        return {
            'time_instances': [j.to_save_data() for j in self.time_instances],
        }

    def respond(self, msg, outputcb):
        return defer.DeferredList([j.reply_to_text(msg, outputcb) for j in self.time_instances])

    def privmsg(self, bot, user, channel, msg):
        return self.respond(msg, lambda r: bot.address_msg(user, channel, r, prefix=False))

    def action(self, bot, user, channel, msg):
        return self.respond(msg, lambda r: bot.address_msg(user, channel, r, prefix=False))

    @require_priv('admin')
    @defer.inlineCallbacks
    def command_add_time(self, bot, user, channel, args):
        if len(args) == 2:
            longcode, shortcode = args
        else:
            yield bot.address_msg(user, channel, 'usage: add-timecode <longcode> [<shortcode>]')
            return
        self.time_instances.append(TimeInstance(longcode, shortcode))

    @require_priv('admin')
    @defer.inlineCallbacks
    def command_list_times(self, bot, user, channel, args):
        if len(args) > 0:
            yield bot.address_msg(user, channel, 'usage: list-jiras')
            return
        for j in self.time_instances:
            yield bot.address_msg(user, channel, '%s: shortcode=%r' % (j.longcode, j.shortcode))
