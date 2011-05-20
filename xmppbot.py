# xmpp MUCClient -> IRCClient adapter

from twisted.words.protocols.jabber import jid
from twisted.words.xish import domish
from twisted.internet import task, defer
from twisted.python import log
from wokkel.client import XMPPClient
from wokkel import muc
import cassbot

class XMPPCassBotAdapter(cassbot.CassBotCore):
    """
    Override the minimal set of methods of CassBotCore necessary to make it
    work nicely with XMPP.
    """

    def join(self, channel, key=None):
        if key is not None:
            raise NotImplemented("can't use channel keys through xmpp client")
        return self.factory.chanjoin(channel)

    def leave(self, channel, reason=None):
        return self.factory.leave(channel)

    def kick(self, channel, user, reason=None):
        raise NotImplemented("can't kick through xmpp client")

    def invite(self, user, channel):
        raise NotImplemented("can't invite through xmpp client")

    def topic(self, channel, topic=None):
        raise NotImplemented("can't set topic through xmpp client")

    def mode(self, chan, set, modes, limit=None, user=None, mask=None):
        raise NotImplemented("can't set modes through xmpp client")

    def say(self, channel, message, length=None):
        return self.msg(channel, message, length=length)

    def msg(self, room_or_user, message, length=None):
        return self.factory.sendmsg(room_or_user, message)

    def notice(self, user, message):
        return self.msg(user, message)

    def away(self, message=''):
        raise NotImplemented("can't set away through xmpp client")

    def whois(self, nickname, server=None):
        raise NotImplemented("can't query whois through xmpp client")

    def register(self, nickname, hostname='foo', servername='bar'):
        raise NotImplemented("register shouldn't be called through xmpp client")

    def setNick(self, nickname):
        raise NotImplemented("can't change nick through xmpp client")

    def quit(self, message=''):
        raise NotImplemented("can't quit through xmpp client")

    def describe(self, channel, action):
        return self.msg(channel, '/me ' + action)

    def ping(self, user, text=None):
        raise NotImplemented("can't ping another user through xmpp client")

    def requestChannelMode(self, channel):
        pass

class XMPPCassBot(muc.MUCClient):
    mode = 'xmpp'
    ping_interval = 120
    adapter_class = XMPPCassBotAdapter
    prot = None

    def __init__(self, botservice, nickname='cassbot'):
        muc.MUCClient.__init__(self)
        self.botservice = botservice
        self.nickname = nickname

    def my_jid(self):
        return self.parent.factory.authenticator.jid.full()

    def initialized(self):
        self.xmlstream.addObserver(muc.CHAT_BODY, self._onPrivateChat)

        prot = self.adapter_class(nickname=self.nickname.encode('utf-8'))
        prot.service = self.botservice
        prot.factory = self
        self.botservice.initialize_proto_state(prot)
        prot.signedOn()

        self.pinglooper = task.LoopingCall(self.pingServer)
        self.pinglooper.start(self.ping_interval, now=False)

    def resetDelay(self):
        # dummy
        pass

    def connectionLost(self, reason):
        if self.prot:
            self.prot.connectionLost(reason)
        try:
            self.pinglooper.stop()
            del self.pinglooper
        except AttributeError:
            pass
        log.err(reason, "disconnected")
        return muc.MUCClient.connectionLost(self, reason)

    def chanjoin(self, channel):
        try:
            room, server = channel.split('@', 1)
        except ValueError:
            room = channel
            server = self.conference_server
        try:
            server, nick = server.split('/', 1)
        except ValueError:
            nick = self.nickname
        d = self.join(server, room, nick)
        d.addCallback(self._joinComplete)
        d.addErrback(log.err, "Could not join %s" % (room,))

    def _joinComplete(self, room):
        userhost = room.occupantJID.userhost()
        d = defer.succeed(None)
        if int(room.status) == muc.STATUS_CODE_CREATED:
            d.addCallback(lambda _: self.getConfigureForm(userhost))
            d.addCallback(lambda _: self.configure(userhost))
        d.addCallback(lambda _: self.prot.joined(self.room2chan(room)) if self.prot else None)
        return d

    def _onPrivateChat(self, msg):
        if not msg.hasAttribute('from'):
            return
        return self.receivedPrivateChat(msg['from'], msg['body'])

    def sendmsg(self, room_or_user, message):
        if self.is_room(room_or_user):
            self.groupChat(room_or_user, message)
        else:
            xmlmsg = domish.Element((None, 'message'))
            xmlmsg['to'] = room_or_user
            xmlmsg['from'] = self.my_jid()
            xmlmsg['type'] = 'chat'
            xmlmsg.addElement('body', content=message)
            self.send(xmlmsg)

    def is_room(self, roomname):
        occupantJID = jid.internJID(roomname)
        r = self._getRoom(occupantJID)
        return (r is not None)

    def room2chan(self, room):
        return room.occupantJID.full().encode('utf-8')

    def user2nick(self, user):
        return user.nick.encode('utf-8')

    def userJoinedRoom(self, room, user):
        if self.prot:
            self.prot.userJoined(self.user2nick(user), self.room2chan(room))

    def userLeftRoom(self, room, user):
        if self.prot:
            self.prot.userLeft(self.user2nick(user), self.room2chan(room))

    def receivedGroupChat(self, room, user, body):
        channel = self.room2chan(room)
        if user.nick == self.nickname:
            # seeing my own message
            return
        nick = self.user2nick(user)
        if self.prot:
            return self.prot.privmsg(nick, channel, body.encode('utf-8'))

    def receivedPrivateChat(self, user, body):
        if self.prot:
            return self.prot.privmsg(self.user2nick(user), self.prot.nickname,
                                     body.encode('utf-8'))

    def pingServer(self):
        try:
            ping = domish.Element((None, 'iq'))
            ping['from'] = self.my_jid()
            ping['type'] = 'get'
            p = ping.addElement('ping')
            p['xmlns'] = 'urn:xmpp:ping'
            self.send(ping)
        except Exception, e:
            log.err(e, 'could not ping server')


class XMPPCassBotService(cassbot.CassBotService):
    xmppbot = None

    def __init__(self, user_jid, password, jabber_server=None, conference_server=None,
                 nickname=None, init_channels=(), statefile='cassbot.state.db',
                 reactor=None):
        self.jid = jid.internJID(user_jid)
        if nickname is None:
            nickname = self.jid.user

        cassbot.CassBotService.__init__(self, self.jid.full(), nickname=nickname,
                                        init_channels=init_channels, reactor=reactor,
                                        statefile=statefile)

        self.password = password
        if jabber_server is None:
            jabber_server = self.jid.host
        if conference_server is None:
            conference_server = self.jid.host
        self.jabber_server = jabber_server
        self.conference_server = conference_server

    def setupConnectionParams(self, conffile):
        self.endpoint_desc = 'conffile=%s' % (conffile,)

    def setupConnection(self):
        xmppclient = XMPPClient(self.jid, self.password, self.jabber_server)
        xmppclient.logTraffic = False

        xmppbot = XMPPCassBot(self, self.state['nickname'])
        xmppbot.conference_server = self.conference_server
        xmppbot.setHandlerParent(xmppclient)

        xmppclient.setServiceParent(self)

        self.xmppbot = xmppbot
        self.xmppclient = xmppclient

    def teardownConnection(self):
        self.xmppclient.disownServiceParent()
        if self.xmppclient.running:
            self.xmppclient.stopService()
        self.xmppbot = None

    def getbot(self):
        return self.xmppbot


# vim: set et sw=4 ts=4 :
