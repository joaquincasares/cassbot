import os
import shlex
from twisted.internet import reactor
from twisted.application import service

nickname = os.environ.get('nickname', 'CassBotJr')
channels = shlex.split(os.environ.get('channels', ''))
statefile = os.environ.get('statefile', 'cassbot.state.db')

jid = os.environ.get('jid', None)
if jid is not None:
    from xmppbot import XMPPCassBotService
    password = os.environ['password']
    jabber_server = os.environ.get('jabber_server', None)
    conference_server = os.environ.get('conference_server', None)
    bot = XMPPCassBotService(jid, password, jabber_server, conference_server,
                             nickname=nickname, init_channels=channels,
                             statefile=statefile)
else:
    from cassbot import CassBotService
    server = os.environ.get('server', 'tcp:host=irc.freenode.net:port=6667')
    bot = CassBotService(server, nickname=nickname, init_channels=channels,
                         statefile=statefile)

application = service.Application(nickname)
bot.setServiceParent(application)

def setup():
    for modname in shlex.split(os.environ.get('autoload_modules', 'Admin')):
        bot.enable_plugin_by_name(modname)

    auto_admin = os.environ.get('auto_admin', os.environ['LOGNAME'])
    bot.auth.addPriv(auto_admin, 'admin')

reactor.callWhenRunning(setup)
