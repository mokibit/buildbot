# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members

import stat
import tarfile
from io import BytesIO

from mock import Mock

from twisted.internet import defer

from buildbot.util import unicode2bytes


class ExpectRemoteRef:

    """
    Define an expected RemoteReference in the args to an L{Expect} class
    """

    def __init__(self, rrclass):
        self.rrclass = rrclass

    def __eq__(self, other):
        return isinstance(other, self.rrclass)


class Expect:

    """
    Define an expected L{RemoteCommand}, with the same arguments

    Extra behaviors of the remote command can be added to the instance, using
    class methods.  Use L{Expect.log} to add a logfile, L{Expect.update} to add
    an arbitrary update, or add an integer to specify the return code (rc), or
    add a Failure instance to raise an exception. Additionally, use
    L{Expect.behavior}, passing a callable that will be invoked with the real
    command and can do what it likes:

        def custom_behavior(command):
            ...
        Expect('somecommand', { args='foo' })
            + Expect.behavior(custom_behavior),
        ...

        Expect('somecommand', { args='foo' })
            + Expect.log('stdio', stdout='foo!')
            + Expect.log('config.log', stdout='some info')
            + Expect.update('status', 'running').add(0), # (specifies the rc)
        ...

    """

    def __init__(self, remote_command, args, interrupted=False):
        """
        Expect a command named C{remote_command}, with args C{args}.
        """
        self.remote_command = remote_command
        self.args = args
        self.result = None
        self.interrupted = interrupted
        self.connection_broken = False
        self.behaviors = []

    def behavior(self, callable):
        self.behaviors.append(('callable', callable))
        return self

    def error(self, error):
        self.behaviors.append(('err', error))
        return self

    def log(self, name, **streams):
        self.behaviors.append(('log', name, streams))
        return self

    def update(self, name, value):
        self.behaviors.append(('update', name, value))
        return self

    def stdout(self, output):
        self.behaviors.append(('log', 'stdio', {'stdout': output}))
        return self

    def stderr(self, output):
        self.behaviors.append(('log', 'stdio', {'stderr': output}))
        return self

    def exit(self, code):
        self.behaviors.append(('rc', code))
        return self

    def break_connection(self):
        self.connection_broken = True
        return self

    @defer.inlineCallbacks
    def runBehavior(self, behavior, args, command):
        """
        Implement the given behavior.  Returns a Deferred.
        """
        if behavior == 'rc':
            yield command.remoteUpdate({'rc': args[0]})
        elif behavior == 'err':
            raise args[0]
        elif behavior == 'update':
            yield command.remoteUpdate({args[0]: args[1]})
        elif behavior == 'log':
            name, streams = args
            for stream in streams:
                if stream not in ['header', 'stdout', 'stderr']:
                    raise Exception(f'Log stream {stream} is not recognized')

            if name == command.stdioLogName:
                if 'header' in streams:
                    command.addHeader(streams['header'])
                if 'stdout' in streams:
                    command.addStdout(streams['stdout'])
                if 'stderr' in streams:
                    command.addStderr(streams['stderr'])
            else:
                if 'header' in streams or 'stderr' in streams:
                    raise Exception('Non stdio streams only support stdout')
                yield command.addToLog(name, streams['stdout'])
                if name not in command.logs:
                    raise Exception(f"{command}.addToLog: no such log {name}")

        elif behavior == 'callable':
            yield args[0](command)
        else:
            raise AssertionError(f'invalid behavior {behavior}')
        return None

    @defer.inlineCallbacks
    def runBehaviors(self, command):
        """
        Run all expected behaviors for this command
        """
        for behavior in self.behaviors:
            yield self.runBehavior(behavior[0], behavior[1:], command)

    def expectationPassed(self, exp):
        """
        Some expectations need to be able to distinguish pass/fail of
        nested expectations.

        This will get invoked once for every nested exception and once
        for self unless anything fails.  Failures are passed to raiseExpectationFailure for
        handling.

        @param exp: The nested exception that passed or self.
        """

    def raiseExpectationFailure(self, exp, failure):
        """
        Some expectations may wish to suppress failure.
        The default expectation does not.

        This will get invoked if the expectations fails on a command.

        @param exp: the expectation that failed.  this could be self or a nested exception
        """
        raise failure

    def shouldAssertCommandEqualExpectation(self):
        """
        Whether or not we should validate that the current command matches the expectation.
        Some expectations may not have a way to match a command.
        """
        return True

    def shouldRunBehaviors(self):
        """
        Whether or not, once the command matches the expectation,
        the behaviors should be run for this step.
        """
        return True

    def shouldKeepMatchingAfter(self, command):
        """
        Expectations are by default not kept matching multiple commands.

        Return True if you want to re-use a command for multiple commands.
        """
        return False

    def nestedExpectations(self):
        """
        Any sub-expectations that should be validated.
        """
        return []

    def __repr__(self):
        return "Expect(" + repr(self.remote_command) + ")"


class ExpectShell(Expect):

    """
    Define an expected L{RemoteShellCommand}, with the same arguments Any
    non-default arguments must be specified explicitly (e.g., usePTY).
    """

    class NotSet:
        pass

    def __init__(self, workdir, command, env=NotSet,
                 want_stdout=1, want_stderr=1, initial_stdin=None,
                 timeout=20 * 60, max_time=None, sigterm_time=None, logfiles=None,
                 use_pty=False, log_environ=True, interrupt_signal='KILL'):
        if env is self.NotSet:
            env = {}
        if logfiles is None:
            logfiles = {}
        args = {
            'workdir': workdir,
            'command': command,
            'env': env,
            'want_stdout': want_stdout,
            'want_stderr': want_stderr,
            'initial_stdin': initial_stdin,
            'timeout': timeout,
            'maxTime': max_time,
            'logfiles': logfiles,
            'usePTY': use_pty,
            'logEnviron': log_environ
        }

        if sigterm_time is not self.NotSet:
            args['sigtermTime'] = sigterm_time
        if interrupt_signal is not None:
            args['interruptSignal'] = interrupt_signal
        super().__init__("shell", args)

    def __repr__(self):
        return "ExpectShell(" + repr(self.remote_command) + repr(self.args['command']) + ")"


class ExpectStat(Expect):

    def __init__(self, file, workdir=None, log_environ=None):
        args = {'file': file}
        if workdir is not None:
            args['workdir'] = workdir
        if log_environ is not None:
            args['logEnviron'] = log_environ

        super().__init__('stat', args)

    def stat(self, mode, inode=99, dev=99, nlink=1, uid=0, gid=0, size=99,
             atime=0, mtime=0, ctime=0):
        self.update('stat', [mode, inode, dev, nlink, uid, gid, size, atime, mtime, ctime])
        return self

    def stat_file(self, mode=0, size=99, atime=0, mtime=0, ctime=0):
        self.stat(stat.S_IFREG, size=size, atime=atime, mtime=mtime, ctime=ctime)
        return self

    def stat_dir(self, mode=0, size=99, atime=0, mtime=0, ctime=0):
        self.stat(stat.S_IFDIR, size=size, atime=atime, mtime=mtime, ctime=ctime)
        return self

    def __repr__(self):
        return "ExpectStat(" + repr(self.args['file']) + ")"


class ExpectUploadFile(Expect):

    def __init__(self, blocksize=None, maxsize=None, workersrc=None, workdir=None,
                 writer=None, keepstamp=None, slavesrc=None, interrupted=False):
        args = {'workdir': workdir, 'writer': writer,
                'blocksize': blocksize, 'maxsize': maxsize}
        if keepstamp is not None:
            args['keepstamp'] = keepstamp
        if slavesrc is not None:
            args['slavesrc'] = slavesrc
        if workersrc is not None:
            args['workersrc'] = workersrc

        super().__init__('uploadFile', args, interrupted=interrupted)

    def upload_string(self, string, timestamp=None, out_writers=None, error=None):
        def behavior(command):
            writer = command.args['writer']
            if out_writers is not None:
                out_writers.append(writer)

            writer.remote_write(string)
            writer.remote_close()
            if timestamp:
                writer.remote_utime(timestamp)

            if error is not None:
                writer.cancel = Mock(wraps=writer.cancel)
                raise error

        self.behavior(behavior)
        return self

    def __repr__(self):
        return f"ExpectUploadFile({repr(self.args['workdir'])},{repr(self.args['workersrc'])})"


class ExpectUploadDirectory(Expect):

    def __init__(self, compress=None, blocksize=None, maxsize=None, workersrc=None, workdir=None,
                 writer=None, keepstamp=None, slavesrc=None, interrupted=False):
        args = {'compress': compress, 'workdir': workdir, 'writer': writer,
                'blocksize': blocksize, 'maxsize': maxsize}
        if keepstamp is not None:
            args['keepstamp'] = keepstamp
        if slavesrc is not None:
            args['slavesrc'] = slavesrc
        if workersrc is not None:
            args['workersrc'] = workersrc

        super().__init__('uploadDirectory', args, interrupted=interrupted)

    def upload_tar_file(self, filename, members, error=None, out_writers=None):
        def behavior(command):
            f = BytesIO()
            archive = tarfile.TarFile(fileobj=f, name=filename, mode='w')  # noqa pylint: disable=consider-using-with
            for name, content in members.items():
                content = unicode2bytes(content)
                archive.addfile(tarfile.TarInfo(name), BytesIO(content))

            writer = command.args['writer']
            if out_writers is not None:
                out_writers.append(writer)

            writer.remote_write(f.getvalue())
            writer.remote_unpack()

            if error is not None:
                writer.cancel = Mock(wraps=writer.cancel)
                raise error

        self.behavior(behavior)
        return self

    def __repr__(self):
        return (f"ExpectUploadDirectory({repr(self.args['workdir'])}, "
                f"{repr(self.args['workersrc'])})")


class ExpectDownloadFile(Expect):

    def __init__(self, blocksize=None, maxsize=None, workerdest=None, workdir=None,
                reader=None, mode=None, interrupted=False, slavesrc=None, slavedest=None):
        args = {'workdir': workdir, 'reader': reader, 'mode': mode,
                'blocksize': blocksize, 'maxsize': maxsize}
        if slavesrc is not None:
            args['slavesrc'] = slavesrc
        if slavedest is not None:
            args['slavedest'] = slavedest
        if workerdest is not None:
            args['workerdest'] = workerdest

        super().__init__('downloadFile', args, interrupted=interrupted)

    def download_string(self, dest_callable, size=1000, timestamp=None):
        def behavior(command):
            reader = command.args['reader']
            read = reader.remote_read(size)

            dest_callable(read)

            reader.remote_close()
            if timestamp:
                reader.remote_utime(timestamp)
            return read

        self.behavior(behavior)
        return self

    def __repr__(self):
        return (f"ExpectUploadDirectory({repr(self.args['workdir'])}, "
                f"{repr(self.args['workerdest'])})")


class ExpectMkdir(Expect):

    def __init__(self, dir=None, log_environ=None):
        args = {'dir': dir}
        if log_environ is not None:
            args['logEnviron'] = log_environ

        super().__init__('mkdir', args)

    def __repr__(self):
        return f"ExpectMkdir({repr(self.args['dir'])})"


class ExpectRmdir(Expect):

    def __init__(self, dir=None, log_environ=None, timeout=None, path=None):
        args = {'dir': dir}
        if log_environ is not None:
            args['logEnviron'] = log_environ
        if timeout is not None:
            args['timeout'] = timeout
        if path is not None:
            args['path'] = path

        super().__init__('rmdir', args)

    def __repr__(self):
        return f"ExpectRmdir({repr(self.args['dir'])})"


class ExpectCpdir(Expect):

    def __init__(self, fromdir=None, todir=None, log_environ=None, timeout=None, max_time=None):
        args = {'fromdir': fromdir, 'todir': todir}
        if log_environ is not None:
            args['logEnviron'] = log_environ
        if timeout is not None:
            args['timeout'] = timeout
        if max_time is not None:
            args['maxTime'] = max_time

        super().__init__('cpdir', args)

    def __repr__(self):
        return f"ExpectCpdir({repr(self.args['fromdir'])}, {repr(self.args['todir'])})"


class ExpectGlob(Expect):

    def __init__(self, path=None, log_environ=None):
        args = {'path': path}
        if log_environ is not None:
            args['logEnviron'] = log_environ

        super().__init__('glob', args)

    def files(self, files=None):
        if files is None:
            files = []
        self.update('files', files)
        return self

    def __repr__(self):
        return f"ExpectGlob({repr(self.args['path'])})"


class ExpectListdir(Expect):

    def __init__(self, dir=None):
        args = {'dir': dir}

        super().__init__('listdir', args)

    def files(self, files=None):
        if files is None:
            files = []
        self.update('files', files)
        return self

    def __repr__(self):
        return f"ExpectListdir({repr(self.args['dir'])})"


class ExpectRmfile(Expect):

    def __init__(self, path=None, log_environ=None):
        args = {'path': path}
        if log_environ is not None:
            args['logEnviron'] = log_environ

        super().__init__('rmfile', args)

    def __repr__(self):
        return f"ExpectRmfile({repr(self.args['path'])})"