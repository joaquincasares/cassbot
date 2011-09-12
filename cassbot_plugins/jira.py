import re
from string import Template
from itertools import chain
from twisted.internet import defer
from twisted.python import log
from twisted.web import soap, error as web_error
from cassbot import BaseBotPlugin, mask_matches, require_priv

def weed_duplicates(elements):
    already = set()
    for e in elements:
        if e not in already:
            already.add(e)
            yield e

def listconcat(iterator_of_iterators):
    return reduce(lambda a,b:a+b, map(list, iterator_of_iterators), [])

class NotAuthenticatedError(Exception):
    pass

class JiraInstance:
    def __init__(self, base_url, projectname, shortcode=None, username=None, password=None):
        self.base_url = base_url.rstrip('/')
        self.set_shortcode(shortcode)
        self.set_projectname(projectname)
        self.username = username
        self.password = password
        self.proxy = self.jira_soap_proxy()
        self.proxy_auth = None
        self.jira_soap_proxy_auth()

    def set_projectname(self, projectname):
        self.projectname = projectname
        self.projectname_re = re.compile(r'''(?:^|[[\s({<>:",@*'~])%s-(?P<num>\d+)\b''' % re.escape(projectname))

    def set_shortcode(self, shortcode):
        self.shortcode = shortcode
        self.shortcode_re = None
        if shortcode is not None:
            self.shortcode_re = re.compile(r'''(?:^|[[\s({<>:",@*'~])%s(?P<num>\d+)\b''' % re.escape(shortcode))

    def jira_soap_proxy(self):
        return soap.Proxy(self.make_jira_soap_url())

    def jira_soap_proxy_auth(self):
        self.proxy.callRemote('login', self.username, self.password) \
                  .addCallback(lambda auth: setattr(self, 'proxy_auth', auth)) \
                  .addErrback(self.jira_soap_proxy_auth_failure)

    def jira_soap_proxy_auth_failure(self, f):
        log.err(f, "Could not authenticate to JIRA")
        self.proxy_auth = None

    def jira_soap_auth_call(self, opname, *args, **kwargs):
        if self.proxy_auth is not None:
            d = self.proxy.callRemote(opname, self.proxy_auth, *args, **kwargs)
        else:
            d = defer.fail(NotAuthenticatedError())
        return d

    def make_jira_soap_url(self):
        return '%s/%s' % (self.base_url, 'rpc/soap/jirasoapservice-v2?wsdl')

    @classmethod
    def from_save_data(cls, savedata):
        return cls(savedata['base_url'], savedata['projectname'], savedata['shortcode'],
                   savedata['username'], savedata['password'])

    def to_save_data(self):
        return {'base_url': self.base_url, 'projectname': self.projectname, 'shortcode': self.shortcode,
                'username': self.username, 'password': self.password}

    def find_ticket_references(self, message):
        return listconcat(r.finditer(message) for r in (self.shortcode_re, self.projectname_re) if r)

    def make_link(self, ticketnum):
        return '%s/browse/%s-%d' % (self.base_url, self.projectname, ticketnum)

    def fetch_ticket_info(self, ticketnum):
        return self.jira_soap_auth_call('getIssue', '%s-%d' % (self.projectname, ticketnum))

    @defer.inlineCallbacks
    def link_ticket(self, ticketnum):
        ticket_url = self.make_link(ticketnum)
        try:
            ticketdata = yield self.fetch_ticket_info(ticketnum)
        except (NotAuthenticatedError, web_error.Error), e:
            defer.returnValue(ticket_url)
        defer.returnValue('%s : %s' % (ticket_url, ticketdata.summary))

    def reply_to_text(self, message, outputcb):
        ticketnums = weed_duplicates([int(g.group('num')) for g in self.find_ticket_references(message)])
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

    @require_priv('admin')
    @defer.inlineCallbacks
    def command_add_jira(self, bot, user, channel, args):
        if len(args) == 2:
            args = list(args) + [None]
        if len(args) == 3:
            args = list(args) + [None, None]
        if len(args) == 5:
            base_url, projectname, shortcode, username, password = args
        else:
            yield bot.address_msg(user, channel, 'usage: add-jira <base_url> <projectname> [<shortcode> [<username> <password>]]')
            return
        self.jira_instances.append(JiraInstance(base_url, projectname, shortcode, username, password))

    @require_priv('admin')
    @defer.inlineCallbacks
    def command_list_jiras(self, bot, user, channel, args):
        if len(args) > 0:
            yield bot.address_msg(user, channel, 'usage: list-jiras')
            return
        for j in self.jira_instances:
            yield bot.address_msg(user, channel, '%s: base_url=%r, shortcode=%r' % (j.projectname, j.base_url, j.shortcode))
