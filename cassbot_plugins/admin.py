from cassbot import (BaseBotPlugin, enabled_but_not_found, require_priv,
                     require_priv_in_channel, natural_list)
from twisted.internet import defer
from twisted.python import failure, log
from twisted.plugin import getModule

def makelist(i):
    return ', '.join(sorted(i)) if i else 'none'

class Admin(BaseBotPlugin):
    @defer.inlineCallbacks
    def command_modules(self, bot, user, channel, args):
        if args:
            yield bot.address_msg(channel, "usage: modules")
            return

        notfound = set()
        loaded = set()
        available = set()
        for name, p in bot.service.pluginmap.iteritems():
            if isinstance(p, enabled_but_not_found):
                notfound.add(name)
            else:
                loaded.add(name)
        available = set(p.name() for p in bot.service.get_plugin_classes()) \
                    - notfound - loaded

        output = ['loaded modules: %s' % makelist(loaded)]
        if notfound:
            output.append('modules enabled but not found: %s' % makelist(notfound))
        output.append('other available modules: %s' % makelist(available))
        yield bot.address_msg(user, channel, '\n'.join(output))

    @require_priv('admin')
    @defer.inlineCallbacks
    def command_modenable(self, bot, user, channel, args):
        if len(args) == 0:
            yield bot.address_msg(user, channel, 'usage: modenable [modulenames]')
            return
        for arg in args:
            output = self.do_mod_enable(bot.service, arg)
            yield bot.address_msg(user, channel, output)

    def do_mod_enable(self, serv, modname):
        d = serv.enable_plugin_by_name(modname)
        if d.called:
            if isinstance(d.result, failure.Failure):
                err = d.result.value
                return 'Problem loading %s: [%s] %s' \
                       % (modname, err.type.__name__, err.value)
            else:
                return 'Module %s loaded.' % modname
        else:
            return 'Module %s marked for loading once it is found.' % modname

    @require_priv('admin')
    @defer.inlineCallbacks
    def command_moddisable(self, bot, user, channel, args):
        if len(args) == 0:
            yield bot.address_msg(user, channel, 'usage: moddisable [modulenames]')
            return
        for arg in args:
            if arg not in bot.service.pluginmap:
                yield bot.address_msg(user, channel, 'Module %s is not loaded.' % arg)
                continue
            bot.service.disable_plugin(arg)
            yield bot.address_msg(user, channel, 'Module %s disabled.' % arg)

    @require_priv('admin')
    @defer.inlineCallbacks
    def command_modreload(self, bot, user, channel, args):
        if len(args) == 0:
            yield bot.address_msg(user, channel, 'usage: modreload [modulenames]')
            return
        for arg in args:
            output = self.do_mod_reload(bot.service, arg)
            yield bot.address_msg(user, channel, output)

    @require_priv('admin')
    @defer.inlineCallbacks
    def command_join(self, bot, user, channel, args):
        if len(args) != 1:
            yield bot.address_msg(user, channel, 'usage: join [channelname]')
            return
        try:
            bot.join(args[0])
        except Exception:
            f = failure.Failure()
            yield bot.address_msg(user, channel, f.getErrorMessage())
            log.err(f, "Attempting to join %r on command from %r" % (args[0], user))
        else:
            yield bot.address_msg(user, channel, 'kay.')

    @require_priv('admin')
    @defer.inlineCallbacks
    def command_part(self, bot, user, channel, args):
        if len(args) == 0 and channel != bot.nickname:
            args = [channel]
        elif len(args) != 1:
            yield bot.address_msg(user, channel, 'usage: part [channelname]')
            return
        try:
            bot.service.leave(args[0])
        except Exception:
            f = failure.Failure()
            yield bot.address_msg(user, channel, f.getErrorMessage())
            log.err(f, "Attempting to part %r on command from %r" % (args[0], user))
        else:
            yield bot.address_msg(user, channel, 'kay.')

    @require_priv('admin')
    @defer.inlineCallbacks
    def command_channels(self, bot, user, channel, args):
        if len(args) != 0:
            yield bot.address_msg(user, channel, 'usage: channels')
            return
        yield bot.address_msg(user, channel, 'configured to join: %s'
                                             % natural_list(sorted(bot.join_channels)))

    @require_priv('admin')
    def command_die(self, bot, user, channel, args):
        bot.service.reactor.callLater(0, bot.service.stopService)

    def do_mod_reload(self, serv, modname):
        try:
            p = serv.pluginmap[modname]
        except KeyError:
            return 'Module %s is not loaded.' % modname
        mod = getModule(p.__module__).load()
        reload(mod)
        serv.disable_plugin(modname)
        return self.do_mod_enable(serv, modname)
