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

def listconcat(iterator_of_iterators):
    return reduce(lambda a,b:a+b, map(list, iterator_of_iterators), [])

class JiraInstance:
    def __init__(self, base_url, projectname, shortcode=None, username=None, password=None):
        self.base_url = base_url
        self.projectname = projectname
        self.shortcode = shortcode
        self.username = username
        self.password = password

    @classmethod
    def from_save_data(cls, savedata):
        return cls(savedata['base_url'], savedata['projectname'], savedata['shortcode'],
                   savedata['username'], savedata['password'])

    def to_save_data(self):
        return {'base_url': self.base_url, 'projectname': self.projectname, 'shortcode': self.shortcode,
                'username': self.username, 'password': self.password}

    def find_ticket_references(self, message):
        return listconcat(r.finditer(message) for r in (self.shortcode_re, self.projectname_re))

    def make_link(self, ticketnum):
        return '%s/browse/%s-%d' % (self.base_url, self.projectname, ticketnum)

    def link_ticket(self, ticketnum):
        return defer.succeed(self.make_link(ticketnum))

    def reply_to_text(self, message, outputcb):
        ticketnums = weed_duplicates(self.find_ticket_references(message))
        return defer.DeferredList([self.link_ticket(tnum).addCallback(outputcb) for tnum in ticketnums])

class JiraIntegration(BaseBotPlugin):
    def __init__(self):
        BaseBotPlugin.__init__(self)
        self.jira_instances = []
        self.link_ignore_list = []

    def loadState(self, state):
        self.link_ignore_list = state.get('link_ignore_list', [])
        instance_data = state.get('jira_instances', [])
        self.jira_instances = map(JiraInstance.from_save_data, instance_data)

    def saveState(self):
        return {
            'link_ignore_list': self.link_ignore_list,
            'jira_instances': [j.to_save_data() for j in self.jira_instances],
        }

    @defer.inlineCallbacks
    def respond(self, msg, outputcb):
        return defer.DeferredList([j.reply_to_text(msg, outputcb) for j in self.jira_instances])

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
