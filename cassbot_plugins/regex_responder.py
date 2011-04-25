import re
from string import Template
from itertools import chain
from twisted.internet import defer
from cassbot import BaseBotPlugin, mask_matches

def weed_duplicates(elements):
    already = set()
    for e in elements:
        if e not in already:
            already.add(e)
            yield e

class RegexResponder(BaseBotPlugin):
    def __init__(self):
        BaseBotPlugin.__init__(self)
        self.response_rules = []
        self.link_ignore_list = []

    def loadState(self, state):
        self.link_ignore_list = state.get('link_ignore_list', [])
        newrules = state.get('response_rules', [])
        self.response_rules = [(re.compile(r), sub) for (r, sub) in newrules]

    def saveState(self):
        return {
            'link_ignore_list': self.link_ignore_list,
            'response_rules': [(r.pattern, sub) for (r, sub) in self.response_rules],
        }

    def apply_rule(self, msg, pat, response):
        for m in pat.finditer(msg):
            yield Template(response).safe_substitute(m.groupdict())

    def apply_all_rules(self, msg):
        return chain(*[self.apply_rule(msg, pat, r) for (pat, r) in self.response_rules])

    @defer.inlineCallbacks
    def respond(self, msg, outputcb):
        responses = self.apply_all_rules(msg)
        for response in weed_duplicates(responses):
            yield outputcb(response)

    def privmsg(self, bot, user, channel, msg):
        for m in self.link_ignore_list:
            if mask_matches(m, user):
                return
        return self.respond(msg, lambda r: bot.address_msg(user, channel, r, prefix=False))

    def action(self, bot, user, channel, msg):
        for m in self.link_ignore_list:
            if mask_matches(m, user):
                return
        return self.respond(msg, lambda r: bot.address_msg(user, channel, r, prefix=False))
