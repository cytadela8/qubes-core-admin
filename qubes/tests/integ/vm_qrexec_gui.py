#
# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2014-2015
#                   Marek Marczykowski-Górecki <marmarek@invisiblethingslab.com>
# Copyright (C) 2015  Wojtek Porczyk <woju@invisiblethingslab.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, see <https://www.gnu.org/licenses/>.
#

import asyncio
import multiprocessing
import os
import subprocess
import sys
import tempfile
import unittest

from distutils import spawn

import grp

import qubes.config
import qubes.devices
import qubes.tests
import qubes.vm.appvm
import qubes.vm.templatevm

TEST_DATA = b"0123456789" * 1024


class TC_00_AppVMMixin(object):
    def setUp(self):
        super(TC_00_AppVMMixin, self).setUp()
        self.init_default_template(self.template)
        if self._testMethodName == 'test_210_time_sync':
            self.init_networking()
        self.testvm1 = self.app.add_new_vm(
            qubes.vm.appvm.AppVM,
            label='red',
            name=self.make_vm_name('vm1'),
            template=self.app.domains[self.template])
        self.loop.run_until_complete(self.testvm1.create_on_disk())
        self.testvm2 = self.app.add_new_vm(
            qubes.vm.appvm.AppVM,
            label='red',
            name=self.make_vm_name('vm2'),
            template=self.app.domains[self.template])
        self.loop.run_until_complete(self.testvm2.create_on_disk())
        self.app.save()

    def tearDown(self):
        # socket-based qrexec tests:
        if os.path.exists('/etc/qubes-rpc/test.Socket'):
            os.unlink('/etc/qubes-rpc/test.Socket')
        if hasattr(self, 'service_proc'):
            try:
                self.service_proc.terminate()
                self.loop.run_until_complete(self.service_proc.communicate())
            except ProcessLookupError:
                pass

        super(TC_00_AppVMMixin, self).tearDown()

    def test_000_start_shutdown(self):
        # TODO: wait_for, timeout
        self.loop.run_until_complete(self.testvm1.start())
        self.assertEqual(self.testvm1.get_power_state(), "Running")
        self.loop.run_until_complete(self.wait_for_session(self.testvm1))
        self.loop.run_until_complete(self.testvm1.shutdown(wait=True))
        self.assertEqual(self.testvm1.get_power_state(), "Halted")

    @unittest.skipUnless(spawn.find_executable('xdotool'),
                         "xdotool not installed")
    def test_010_run_xterm(self):
        self.loop.run_until_complete(self.testvm1.start())
        self.assertEqual(self.testvm1.get_power_state(), "Running")

        self.loop.run_until_complete(self.wait_for_session(self.testvm1))
        p = self.loop.run_until_complete(self.testvm1.run('xterm'))
        try:
            title = 'user@{}'.format(self.testvm1.name)
            if self.template.count("whonix"):
                title = 'user@host'
            self.wait_for_window(title)

            self.loop.run_until_complete(asyncio.sleep(0.5))
            subprocess.check_call(
                ['xdotool', 'search', '--name', title,
                'windowactivate', 'type', 'exit\n'])

            self.wait_for_window(title, show=False)
        finally:
            try:
                p.terminate()
                self.loop.run_until_complete(p.wait())
            except ProcessLookupError:  # already dead
                pass

    @unittest.skipUnless(spawn.find_executable('xdotool'),
                         "xdotool not installed")
    def test_011_run_gnome_terminal(self):
        if "minimal" in self.template:
            self.skipTest("Minimal template doesn't have 'gnome-terminal'")
        if 'whonix' in self.template:
            self.skipTest("Whonix template doesn't have 'gnome-terminal'")
        self.loop.run_until_complete(self.testvm1.start())
        self.assertEqual(self.testvm1.get_power_state(), "Running")
        self.loop.run_until_complete(self.wait_for_session(self.testvm1))
        p = self.loop.run_until_complete(self.testvm1.run('gnome-terminal'))
        try:
            title = 'user@{}'.format(self.testvm1.name)
            if self.template.count("whonix"):
                title = 'user@host'
            self.wait_for_window(title)

            self.loop.run_until_complete(asyncio.sleep(0.5))
            subprocess.check_call(
                ['xdotool', 'search', '--name', title,
                'windowactivate', '--sync', 'type', 'exit\n'])

            wait_count = 0
            while subprocess.call(['xdotool', 'search', '--name', title],
                                stdout=open(os.path.devnull, 'w'),
                                stderr=subprocess.STDOUT) == 0:
                wait_count += 1
                if wait_count > 100:
                    self.fail("Timeout while waiting for gnome-terminal "
                            "termination")
                self.loop.run_until_complete(asyncio.sleep(0.1))
        finally:
            try:
                p.terminate()
                self.loop.run_until_complete(p.wait())
            except ProcessLookupError:  # already dead
                pass

    @unittest.skipUnless(spawn.find_executable('xdotool'),
                         "xdotool not installed")
    def test_012_qubes_desktop_run(self):
        self.loop.run_until_complete(self.testvm1.start())
        self.assertEqual(self.testvm1.get_power_state(), "Running")
        xterm_desktop_path = "/usr/share/applications/xterm.desktop"
        # Debian has it different...
        xterm_desktop_path_debian = \
            "/usr/share/applications/debian-xterm.desktop"
        try:
            self.loop.run_until_complete(self.testvm1.run_for_stdio(
                'test -r {}'.format(xterm_desktop_path_debian)))
        except subprocess.CalledProcessError:
            pass
        else:
            xterm_desktop_path = xterm_desktop_path_debian
        self.loop.run_until_complete(self.wait_for_session(self.testvm1))
        self.loop.run_until_complete(
            self.testvm1.run('qubes-desktop-run {}'.format(xterm_desktop_path)))
        title = 'user@{}'.format(self.testvm1.name)
        if self.template.count("whonix"):
            title = 'user@host'
        self.wait_for_window(title)

        self.loop.run_until_complete(asyncio.sleep(0.5))
        subprocess.check_call(
            ['xdotool', 'search', '--name', title,
             'windowactivate', '--sync', 'type', 'exit\n'])

        self.wait_for_window(title, show=False)

    def test_050_qrexec_simple_eof(self):
        """Test for data and EOF transmission dom0->VM"""

        # XXX is this still correct? this is no longer simple qrexec,
        # but qubes.VMShell

        self.loop.run_until_complete(self.testvm1.start())
        try:
            (stdout, stderr) = self.loop.run_until_complete(asyncio.wait_for(
                self.testvm1.run_for_stdio('cat', input=TEST_DATA),
                timeout=10))
        except asyncio.TimeoutError:
            self.fail(
                "Timeout, probably EOF wasn't transferred to the VM process")

        self.assertEqual(stdout, TEST_DATA,
            'Received data differs from what was sent')
        self.assertFalse(stderr,
            'Some data was printed to stderr')

    def test_051_qrexec_simple_eof_reverse(self):
        """Test for EOF transmission VM->dom0"""

        @asyncio.coroutine
        def run(self):
            p = yield from self.testvm1.run(
                    'echo test; exec >&-; cat > /dev/null',
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)

            # this will hang on test failure
            stdout = yield from asyncio.wait_for(p.stdout.read(), timeout=10)

            p.stdin.write(TEST_DATA)
            yield from p.stdin.drain()
            p.stdin.close()
            self.assertEqual(stdout.strip(), b'test',
                'Received data differs from what was expected')
            # this may hang in some buggy cases
            self.assertFalse((yield from p.stderr.read()),
                'Some data was printed to stderr')

            try:
                yield from asyncio.wait_for(p.wait(), timeout=1)
            except asyncio.TimeoutError:
                self.fail("Timeout, "
                    "probably EOF wasn't transferred from the VM process")

        self.loop.run_until_complete(self.testvm1.start())
        self.loop.run_until_complete(self.wait_for_session(self.testvm1))
        self.loop.run_until_complete(run(self))

    def test_052_qrexec_vm_service_eof(self):
        """Test for EOF transmission VM(src)->VM(dst)"""

        self.loop.run_until_complete(asyncio.wait([
            self.testvm1.start(),
            self.testvm2.start()]))
        self.loop.run_until_complete(asyncio.wait([
            self.wait_for_session(self.testvm1),
            self.wait_for_session(self.testvm2)]))
        self.create_remote_file(self.testvm2,
                                '/etc/qubes-rpc/test.EOF',
                                '#!/bin/sh\n/bin/cat\n')

        with self.qrexec_policy('test.EOF', self.testvm1, self.testvm2):
            try:
                stdout, _ = self.loop.run_until_complete(asyncio.wait_for(
                    self.testvm1.run_for_stdio('''\
                        /usr/lib/qubes/qrexec-client-vm {} test.EOF \
                            /bin/sh -c 'echo test; exec >&-; cat >&$SAVED_FD_1'
                    '''.format(self.testvm2.name)),
                    timeout=10))
            except subprocess.CalledProcessError as e:
                self.fail('{} exited with non-zero code {}; stderr: {}'.format(
                    e.cmd, e.returncode, e.stderr))
            except asyncio.TimeoutError:
                self.fail("Timeout, probably EOF wasn't transferred")

        self.assertEqual(stdout, b'test\n',
            'Received data differs from what was expected')

    def test_053_qrexec_vm_service_eof_reverse(self):
        """Test for EOF transmission VM(src)<-VM(dst)"""

        self.loop.run_until_complete(asyncio.wait([
            self.testvm1.start(),
            self.testvm2.start()]))
        self.create_remote_file(self.testvm2, '/etc/qubes-rpc/test.EOF',
                '#!/bin/sh\n'
                'echo test; exec >&-; cat >/dev/null')

        with self.qrexec_policy('test.EOF', self.testvm1, self.testvm2):
            try:
                stdout, _ = self.loop.run_until_complete(asyncio.wait_for(
                    self.testvm1.run_for_stdio('''\
                        /usr/lib/qubes/qrexec-client-vm {} test.EOF \
                            /bin/sh -c 'cat >&$SAVED_FD_1'
                        '''.format(self.testvm2.name)),
                    timeout=10))
            except subprocess.CalledProcessError as e:
                self.fail('{} exited with non-zero code {}; stderr: {}'.format(
                    e.cmd, e.returncode, e.stderr))
            except asyncio.TimeoutError:
                self.fail("Timeout, probably EOF wasn't transferred")

        self.assertEqual(stdout, b'test\n',
            'Received data differs from what was expected')

    def test_055_qrexec_dom0_service_abort(self):
        """
        Test if service abort (by dom0) is properly handled by source VM.

        If "remote" part of the service terminates, the source part should
        properly be notified. This includes closing its stdin (which is
        already checked by test_053_qrexec_vm_service_eof_reverse), but also
        its stdout - otherwise such service might hang on write(2) call.
        """

        self.loop.run_until_complete(self.testvm1.start())
        self.create_local_file('/etc/qubes-rpc/test.Abort',
            'sleep 1')

        with self.qrexec_policy('test.Abort', self.testvm1, 'dom0'):
            try:
                # two possible exit codes, depending on when exactly dom0
                # service terminates:
                # exit code 141: EPIPE (no buffered data)
                # exit code 1: ECONNRESET (some buffered data remains)
                stdout, _ = self.loop.run_until_complete(asyncio.wait_for(
                    self.testvm1.run_for_stdio('''\
                        /usr/lib/qubes/qrexec-client-vm dom0 test.Abort \
                            /bin/sh -c 'cat /dev/zero; echo $? >/tmp/exit-code';
                            e=$(cat /tmp/exit-code);
                            test $e -eq 141 -o $e -eq 1'''),
                    timeout=10))
            except subprocess.CalledProcessError as e:
                self.fail('{} exited with non-zero code {}; stderr: {}'.format(
                    e.cmd, e.returncode, e.stderr))
            except asyncio.TimeoutError:
                self.fail("Timeout, probably stdout wasn't closed")

    def test_060_qrexec_exit_code_dom0(self):
        self.loop.run_until_complete(self.testvm1.start())
        self.loop.run_until_complete(self.testvm1.run_for_stdio('exit 0'))
        with self.assertRaises(subprocess.CalledProcessError) as e:
            self.loop.run_until_complete(self.testvm1.run_for_stdio('exit 3'))
        self.assertEqual(e.exception.returncode, 3)

    def test_065_qrexec_exit_code_vm(self):
        self.loop.run_until_complete(asyncio.wait([
            self.testvm1.start(),
            self.testvm2.start()]))

        with self.qrexec_policy('test.Retcode', self.testvm1, self.testvm2):
            self.create_remote_file(self.testvm2, '/etc/qubes-rpc/test.Retcode',
                'exit 0')
            (stdout, stderr) = self.loop.run_until_complete(
                self.testvm1.run_for_stdio('''\
                    /usr/lib/qubes/qrexec-client-vm {} test.Retcode;
                        echo $?'''.format(self.testvm2.name),
                        stderr=None))
            self.assertEqual(stdout, b'0\n')

            self.create_remote_file(self.testvm2, '/etc/qubes-rpc/test.Retcode',
                'exit 3')
            (stdout, stderr) = self.loop.run_until_complete(
                self.testvm1.run_for_stdio('''\
                    /usr/lib/qubes/qrexec-client-vm {} test.Retcode;
                        echo $?'''.format(self.testvm2.name),
                        stderr=None))
            self.assertEqual(stdout, b'3\n')

    def test_070_qrexec_vm_simultaneous_write(self):
        """Test for simultaneous write in VM(src)->VM(dst) connection

            This is regression test for #1347

            Check for deadlock when initially both sides writes a lot of data
            (and not read anything). When one side starts reading, it should
            get the data and the remote side should be possible to write then more.
            There was a bug where remote side was waiting on write(2) and not
            handling anything else.
        """

        self.loop.run_until_complete(asyncio.wait([
            self.testvm1.start(),
            self.testvm2.start()]))

        self.create_remote_file(self.testvm2, '/etc/qubes-rpc/test.write', '''\
            # first write a lot of data
            dd if=/dev/zero bs=993 count=10000 iflag=fullblock
            # and only then read something
            dd of=/dev/null bs=993 count=10000 iflag=fullblock
            ''')

        with self.qrexec_policy('test.write', self.testvm1, self.testvm2):
            try:
                self.loop.run_until_complete(asyncio.wait_for(
                    # first write a lot of data to fill all the buffers
                    # then after some time start reading
                    self.testvm1.run_for_stdio('''\
                        /usr/lib/qubes/qrexec-client-vm {} test.write \
                                /bin/sh -c '
                            dd if=/dev/zero bs=993 count=10000 iflag=fullblock &
                            sleep 1;
                            dd of=/dev/null bs=993 count=10000 iflag=fullblock;
                            wait'
                        '''.format(self.testvm2.name)), timeout=10))
            except subprocess.CalledProcessError as e:
                self.fail('{} exited with non-zero code {}; stderr: {}'.format(
                    e.cmd, e.returncode, e.stderr))
            except asyncio.TimeoutError:
                self.fail('Timeout, probably deadlock')

    def test_071_qrexec_dom0_simultaneous_write(self):
        """Test for simultaneous write in dom0(src)->VM(dst) connection

            Similar to test_070_qrexec_vm_simultaneous_write, but with dom0
            as a source.
        """

        self.loop.run_until_complete(self.testvm2.start())

        self.create_remote_file(self.testvm2, '/etc/qubes-rpc/test.write', '''\
            # first write a lot of data
            dd if=/dev/zero bs=993 count=10000 iflag=fullblock
            # and only then read something
            dd of=/dev/null bs=993 count=10000 iflag=fullblock
            ''')

        # can't use subprocess.PIPE, because asyncio will claim those FDs
        pipe1_r, pipe1_w = os.pipe()
        pipe2_r, pipe2_w = os.pipe()
        try:
            local_proc = self.loop.run_until_complete(
                asyncio.create_subprocess_shell(
                    # first write a lot of data to fill all the buffers
                    "dd if=/dev/zero bs=993 count=10000 iflag=fullblock & "
                    # then after some time start reading
                    "sleep 1; "
                    "dd of=/dev/null bs=993 count=10000 iflag=fullblock; "
                    "wait", stdin=pipe1_r, stdout=pipe2_w))

            self.service_proc = self.loop.run_until_complete(self.testvm2.run_service(
                "test.write", stdin=pipe2_r, stdout=pipe1_w))
        finally:
            os.close(pipe1_r)
            os.close(pipe1_w)
            os.close(pipe2_r)
            os.close(pipe2_w)

        try:
            self.loop.run_until_complete(
                asyncio.wait_for(self.service_proc.wait(), timeout=10))
        except asyncio.TimeoutError:
            self.fail("Timeout, probably deadlock")
        else:
            self.assertEqual(self.service_proc.returncode, 0,
                "Service call failed")

    def test_072_qrexec_to_dom0_simultaneous_write(self):
        """Test for simultaneous write in dom0(src)<-VM(dst) connection

            Similar to test_071_qrexec_dom0_simultaneous_write, but with dom0
            as a "hanging" side.
        """

        self.loop.run_until_complete(self.testvm2.start())

        self.create_remote_file(self.testvm2, '/etc/qubes-rpc/test.write', '''\
            # first write a lot of data
            dd if=/dev/zero bs=993 count=10000 iflag=fullblock &
            # and only then read something
            dd of=/dev/null bs=993 count=10000 iflag=fullblock
            sleep 1;
            wait
            ''')

        # can't use subprocess.PIPE, because asyncio will claim those FDs
        pipe1_r, pipe1_w = os.pipe()
        pipe2_r, pipe2_w = os.pipe()
        try:
            local_proc = self.loop.run_until_complete(
                asyncio.create_subprocess_shell(
                    # first write a lot of data to fill all the buffers
                    "dd if=/dev/zero bs=993 count=10000 iflag=fullblock & "
                    # then, only when all written, read something
                    "dd of=/dev/null bs=993 count=10000 iflag=fullblock; ",
                    stdin=pipe1_r, stdout=pipe2_w))

            self.service_proc = self.loop.run_until_complete(
                self.testvm2.run_service(
                    "test.write", stdin=pipe2_r, stdout=pipe1_w))
        finally:
            os.close(pipe1_r)
            os.close(pipe1_w)
            os.close(pipe2_r)
            os.close(pipe2_w)

        try:
            self.loop.run_until_complete(
                asyncio.wait_for(self.service_proc.wait(), timeout=10))
        except asyncio.TimeoutError:
            self.fail("Timeout, probably deadlock")
        else:
            self.assertEqual(self.service_proc.returncode, 0,
                "Service call failed")

    def test_080_qrexec_service_argument_allow_default(self):
        """Qrexec service call with argument"""

        self.loop.run_until_complete(asyncio.wait([
            self.testvm1.start(),
            self.testvm2.start()]))

        self.create_remote_file(self.testvm2, '/etc/qubes-rpc/test.Argument',
            '/usr/bin/printf %s "$1"')
        with self.qrexec_policy('test.Argument', self.testvm1, self.testvm2):
            stdout, stderr = self.loop.run_until_complete(
                self.testvm1.run_for_stdio('/usr/lib/qubes/qrexec-client-vm '
                    '{} test.Argument+argument'.format(self.testvm2.name),
                    stderr=None))
            self.assertEqual(stdout, b'argument')

    def test_081_qrexec_service_argument_allow_specific(self):
        """Qrexec service call with argument - allow only specific value"""

        self.loop.run_until_complete(asyncio.wait([
            self.testvm1.start(),
            self.testvm2.start()]))

        self.create_remote_file(self.testvm2, '/etc/qubes-rpc/test.Argument',
            '/usr/bin/printf %s "$1"')

        with self.qrexec_policy('test.Argument', '$anyvm', '$anyvm', False):
            with self.qrexec_policy('test.Argument+argument',
                    self.testvm1.name, self.testvm2.name):
                stdout, stderr = self.loop.run_until_complete(
                    self.testvm1.run_for_stdio(
                        '/usr/lib/qubes/qrexec-client-vm '
                        '{} test.Argument+argument'.format(self.testvm2.name),
                        stderr=None))
        self.assertEqual(stdout, b'argument')

    def test_082_qrexec_service_argument_deny_specific(self):
        """Qrexec service call with argument - deny specific value"""
        self.loop.run_until_complete(asyncio.wait([
            self.testvm1.start(),
            self.testvm2.start()]))

        self.create_remote_file(self.testvm2, '/etc/qubes-rpc/test.Argument',
            '/usr/bin/printf %s "$1"')
        with self.qrexec_policy('test.Argument', '$anyvm', '$anyvm'):
            with self.qrexec_policy('test.Argument+argument',
                    self.testvm1, self.testvm2, allow=False):
                with self.assertRaises(subprocess.CalledProcessError,
                        msg='Service request should be denied'):
                    self.loop.run_until_complete(
                        self.testvm1.run_for_stdio(
                            '/usr/lib/qubes/qrexec-client-vm {} '
                            'test.Argument+argument'.format(self.testvm2.name),
                            stderr=None))

    def test_083_qrexec_service_argument_specific_implementation(self):
        """Qrexec service call with argument - argument specific
        implementatation"""
        self.loop.run_until_complete(asyncio.wait([
            self.testvm1.start(),
            self.testvm2.start()]))

        self.create_remote_file(self.testvm2,
            '/etc/qubes-rpc/test.Argument',
            '/usr/bin/printf %s "$1"')
        self.create_remote_file(self.testvm2,
            '/etc/qubes-rpc/test.Argument+argument',
            '/usr/bin/printf "specific: %s" "$1"')

        with self.qrexec_policy('test.Argument', self.testvm1, self.testvm2):
            stdout, stderr = self.loop.run_until_complete(
                self.testvm1.run_for_stdio('/usr/lib/qubes/qrexec-client-vm '
                    '{} test.Argument+argument'.format(self.testvm2.name),
                    stderr=None))

        self.assertEqual(stdout, b'specific: argument')

    def test_084_qrexec_service_argument_extra_env(self):
        """Qrexec service call with argument - extra env variables"""
        self.loop.run_until_complete(asyncio.wait([
            self.testvm1.start(),
            self.testvm2.start()]))

        self.create_remote_file(self.testvm2, '/etc/qubes-rpc/test.Argument',
            '/usr/bin/printf "%s %s" '
                '"$QREXEC_SERVICE_FULL_NAME" "$QREXEC_SERVICE_ARGUMENT"')

        with self.qrexec_policy('test.Argument', self.testvm1, self.testvm2):
            stdout, stderr = self.loop.run_until_complete(
                self.testvm1.run_for_stdio('/usr/lib/qubes/qrexec-client-vm '
                    '{} test.Argument+argument'.format(self.testvm2.name),
                    stderr=None))

        self.assertEqual(stdout, b'test.Argument+argument argument')

    def test_090_qrexec_service_socket_dom0(self):
        """Basic test socket services (dom0) - data receive"""
        self.loop.run_until_complete(self.testvm1.start())

        self.service_proc = self.loop.run_until_complete(
            asyncio.create_subprocess_shell(
                'socat -u UNIX-LISTEN:/etc/qubes-rpc/test.Socket,mode=666 -',
                stdout=subprocess.PIPE, stdin=subprocess.PIPE))

        try:
            with self.qrexec_policy('test.Socket', self.testvm1, '@adminvm'):
                (stdout, stderr) = self.loop.run_until_complete(asyncio.wait_for(
                    self.testvm1.run_for_stdio(
                        'qrexec-client-vm @adminvm test.Socket', input=TEST_DATA),
                    timeout=10))
        except subprocess.CalledProcessError as e:
            self.fail('{} exited with non-zero code {}; stderr: {}'.format(
                e.cmd, e.returncode, e.stderr))
        except asyncio.TimeoutError:
            self.fail(
                "service timeout, probably EOF wasn't transferred to the VM process")

        try:
            (service_stdout, service_stderr) = self.loop.run_until_complete(
                asyncio.wait_for(
                    self.service_proc.communicate(),
                    timeout=10))
        except asyncio.TimeoutError:
            self.fail(
                "socat timeout, probably EOF wasn't transferred to the VM process")

        service_descriptor = b'test.Socket+ test-inst-vm1 keyword adminvm\0'
        self.assertEqual(service_stdout, service_descriptor + TEST_DATA,
            'Received data differs from what was sent')
        self.assertFalse(stderr,
            'Some data was printed to stderr')
        self.assertFalse(service_stderr,
            'Some data was printed to stderr')

    def test_091_qrexec_service_socket_dom0_send(self):
        """Basic test socket services (dom0) - data send"""
        self.loop.run_until_complete(self.testvm1.start())

        self.create_local_file('/tmp/service-input', TEST_DATA.decode())

        self.service_proc = self.loop.run_until_complete(
            asyncio.create_subprocess_shell(
                'socat -u OPEN:/tmp/service-input UNIX-LISTEN:/etc/qubes-rpc/test.Socket,mode=666'))

        try:
            with self.qrexec_policy('test.Socket', self.testvm1, '@adminvm'):
                stdout, stderr = self.loop.run_until_complete(asyncio.wait_for(
                    self.testvm1.run_for_stdio(
                        'qrexec-client-vm @adminvm test.Socket'),
                    timeout=10))
        except subprocess.CalledProcessError as e:
            self.fail('{} exited with non-zero code {}; stderr: {}'.format(
                e.cmd, e.returncode, e.stderr))
        except asyncio.TimeoutError:
            self.fail(
                "service timeout, probably EOF wasn't transferred to the VM process")

        try:
            (service_stdout, service_stderr) = self.loop.run_until_complete(
                asyncio.wait_for(
                    self.service_proc.communicate(),
                    timeout=10))
        except asyncio.TimeoutError:
            self.fail(
                "socat timeout, probably EOF wasn't transferred to the VM process")

        self.assertEqual(stdout, TEST_DATA,
            'Received data differs from what was sent')
        self.assertFalse(stderr,
            'Some data was printed to stderr')
        self.assertFalse(service_stderr,
            'Some data was printed to stderr')

    def test_092_qrexec_service_socket_dom0_eof_reverse(self):
        """Test for EOF transmission dom0(socket)->VM"""

        self.loop.run_until_complete(self.testvm1.start())

        self.create_local_file(
            '/tmp/service_script',
            '#!/usr/bin/python3\n'
            'import socket, os, sys, time\n'
            's = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n'
            'os.umask(0)\n'
            's.bind("/etc/qubes-rpc/test.Socket")\n'
            's.listen(1)\n'
            'conn, addr = s.accept()\n'
            'conn.send(b"test\\n")\n'
            'conn.shutdown(socket.SHUT_WR)\n'
            # wait longer than the timeout below
            'time.sleep(15)\n'
        )

        self.service_proc = self.loop.run_until_complete(
            asyncio.create_subprocess_shell('python3 /tmp/service_script',
                stdout=subprocess.PIPE, stdin=subprocess.PIPE))

        try:
            with self.qrexec_policy('test.Socket', self.testvm1, '@adminvm'):
                p = self.loop.run_until_complete(self.testvm1.run(
                        'qrexec-client-vm @adminvm test.Socket',
                        stdout=subprocess.PIPE, stdin=subprocess.PIPE))

                stdout = self.loop.run_until_complete(asyncio.wait_for(
                    p.stdout.read(),
                    timeout=10))
        except asyncio.TimeoutError:
            self.fail(
                "service timeout, probably EOF wasn't transferred from the VM process")

        self.assertEqual(stdout, b'test\n',
            'Received data differs from what was expected')

    def test_093_qrexec_service_socket_dom0_eof(self):
        """Test for EOF transmission VM->dom0(socket)"""

        self.loop.run_until_complete(self.testvm1.start())


        self.create_local_file(
            '/tmp/service_script',
            '#!/usr/bin/python3\n'
            'import socket, os, sys, time\n'
            's = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n'
            'os.umask(0)\n'
            's.bind("/etc/qubes-rpc/test.Socket")\n'
            's.listen(1)\n'
            'conn, addr = s.accept()\n'
            'buf = conn.recv(100)\n'
            'sys.stdout.buffer.write(buf)\n'
            'buf = conn.recv(10)\n'
            'sys.stdout.buffer.write(buf)\n'
            'sys.stdout.buffer.flush()\n'
            'os.close(1)\n'
            # wait longer than the timeout below
            'time.sleep(15)\n'
        )

        self.service_proc = self.loop.run_until_complete(
            asyncio.create_subprocess_shell('python3 /tmp/service_script',
                stdout=subprocess.PIPE, stdin=subprocess.PIPE))

        try:
            with self.qrexec_policy('test.Socket', self.testvm1, '@adminvm'):
                p = self.loop.run_until_complete(self.testvm1.run(
                        'qrexec-client-vm @adminvm test.Socket',
                        stdin=subprocess.PIPE))

                p.stdin.write(b'test1test2')
                p.stdin.write_eof()

                service_stdout = self.loop.run_until_complete(asyncio.wait_for(
                    self.service_proc.stdout.read(),
                    timeout=10))
        except asyncio.TimeoutError:
            self.fail(
                "service timeout, probably EOF wasn't transferred from the VM process")

        service_descriptor = b'test.Socket+ test-inst-vm1 keyword adminvm\0'
        self.assertEqual(service_stdout, service_descriptor + b'test1test2',
            'Received data differs from what was expected')

    def _wait_for_socket_setup(self):
        try:
            self.loop.run_until_complete(asyncio.wait_for(
                self.testvm1.run_for_stdio(
                    'while ! test -e /etc/qubes-rpc/test.Socket; do sleep 0.1; done'),
                timeout=10))
        except asyncio.TimeoutError:
            self.fail(
                "waiting for /etc/qubes-rpc/test.Socket in VM timed out")

    def test_095_qrexec_service_socket_vm(self):
        """Basic test socket services (VM) - receive"""
        self.loop.run_until_complete(self.testvm1.start())

        self.service_proc = self.loop.run_until_complete(self.testvm1.run(
            'socat -u UNIX-LISTEN:/etc/qubes-rpc/test.Socket,mode=666 -',
            stdout=subprocess.PIPE, stdin=subprocess.PIPE,
            user='root'))

        self._wait_for_socket_setup()

        try:
            (stdout, stderr) = self.loop.run_until_complete(asyncio.wait_for(
                self.testvm1.run_service_for_stdio('test.Socket+', input=TEST_DATA),
                timeout=10))
        except subprocess.CalledProcessError as e:
            self.fail('{} exited with non-zero code {}; stderr: {}'.format(
                e.cmd, e.returncode, e.stderr))
        except asyncio.TimeoutError:
            self.fail(
                "service timeout, probably EOF wasn't transferred to the VM process")

        try:
            (service_stdout, service_stderr) = self.loop.run_until_complete(
                asyncio.wait_for(
                    self.service_proc.communicate(),
                    timeout=10))
        except asyncio.TimeoutError:
            self.fail(
                "socat timeout, probably EOF wasn't transferred to the VM process")

        service_descriptor = b'test.Socket+ dom0\0'
        self.assertEqual(service_stdout, service_descriptor + TEST_DATA,
            'Received data differs from what was sent')
        self.assertFalse(stderr,
            'Some data was printed to stderr')
        self.assertFalse(service_stderr,
            'Some data was printed to stderr')

    def test_096_qrexec_service_socket_vm_send(self):
        """Basic test socket services (VM) - send"""
        self.loop.run_until_complete(self.testvm1.start())

        self.create_remote_file(self.testvm1,
            '/tmp/service-input',
            TEST_DATA.decode())

        self.service_proc = self.loop.run_until_complete(self.testvm1.run(
            'socat -u OPEN:/tmp/service-input UNIX-LISTEN:/etc/qubes-rpc/test.Socket,mode=666',
            user='root'))

        self._wait_for_socket_setup()

        try:
            (stdout, stderr) = self.loop.run_until_complete(asyncio.wait_for(
                self.testvm1.run_service_for_stdio('test.Socket+'),
                timeout=10))
        except subprocess.CalledProcessError as e:
            self.fail('{} exited with non-zero code {}; stderr: {}'.format(
                e.cmd, e.returncode, e.stderr))
        except asyncio.TimeoutError:
            self.fail(
                "service timeout, probably EOF wasn't transferred to the VM process")

        try:
            (service_stdout, service_stderr) = self.loop.run_until_complete(
                asyncio.wait_for(
                    self.service_proc.communicate(),
                    timeout=10))
        except asyncio.TimeoutError:
            self.fail(
                "socat timeout, probably EOF wasn't transferred to the VM process")

        self.assertEqual(stdout, TEST_DATA,
            'Received data differs from what was sent')
        self.assertFalse(stderr,
            'Some data was printed to stderr')
        self.assertFalse(service_stderr,
            'Some data was printed to stderr')

    def test_097_qrexec_service_socket_vm_eof_reverse(self):
        """Test for EOF transmission VM(socket)->dom0"""

        self.loop.run_until_complete(self.testvm1.start())

        self.create_remote_file(self.testvm1,
            '/tmp/service_script',
            '#!/usr/bin/python3\n'
            'import socket, os, sys, time\n'
            's = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n'
            'os.umask(0)\n'
            's.bind("/etc/qubes-rpc/test.Socket")\n'
            's.listen(1)\n'
            'conn, addr = s.accept()\n'
            'conn.send(b"test\\n")\n'
            'conn.shutdown(socket.SHUT_WR)\n'
            # wait longer than the timeout below
            'time.sleep(15)\n'
        )

        self.service_proc = self.loop.run_until_complete(self.testvm1.run(
            'python3 /tmp/service_script',
            stdout=subprocess.PIPE, stdin=subprocess.PIPE,
            user='root'))

        self._wait_for_socket_setup()

        try:
            p = self.loop.run_until_complete(
                self.testvm1.run_service('test.Socket+',
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE))
            stdout = self.loop.run_until_complete(asyncio.wait_for(p.stdout.read(),
                timeout=10))
        except asyncio.TimeoutError:
            p.terminate()
            self.fail(
                "service timeout, probably EOF wasn't transferred from the VM process")
        finally:
            self.loop.run_until_complete(p.wait())

        self.assertEqual(stdout,
                b'test\n',
            'Received data differs from what was expected')

    def test_098_qrexec_service_socket_vm_eof(self):
        """Test for EOF transmission dom0->VM(socket)"""

        self.loop.run_until_complete(self.testvm1.start())

        self.create_remote_file(
            self.testvm1,
            '/tmp/service_script',
            '#!/usr/bin/python3\n'
            'import socket, os, sys, time\n'
            's = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n'
            'os.umask(0)\n'
            's.bind("/etc/qubes-rpc/test.Socket")\n'
            's.listen(1)\n'
            'conn, addr = s.accept()\n'
            'buf = conn.recv(100)\n'
            'sys.stdout.buffer.write(buf)\n'
            'buf = conn.recv(10)\n'
            'sys.stdout.buffer.write(buf)\n'
            'sys.stdout.buffer.flush()\n'
            'os.close(1)\n'
            # wait longer than the timeout below
            'time.sleep(15)\n'
        )

        self.service_proc = self.loop.run_until_complete(self.testvm1.run(
            'python3 /tmp/service_script',
            stdout=subprocess.PIPE, stdin=subprocess.PIPE,
            user='root'))

        self._wait_for_socket_setup()

        try:
            p = self.loop.run_until_complete(
                self.testvm1.run_service('test.Socket+',
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE))
            p.stdin.write(b'test1test2')
            self.loop.run_until_complete(
                asyncio.wait_for(p.stdin.drain(), timeout=10))
            p.stdin.close()

            service_stdout = self.loop.run_until_complete(asyncio.wait_for(
                self.service_proc.stdout.read(),
                timeout=10))
        except asyncio.TimeoutError:
            p.terminate()
            self.fail(
                "service timeout, probably EOF wasn't transferred to the VM process")
        finally:
            self.loop.run_until_complete(p.wait())

        service_descriptor = b'test.Socket+ dom0\0'
        self.assertEqual(service_stdout, service_descriptor + b'test1test2',
            'Received data differs from what was expected')

    def test_100_qrexec_filecopy(self):
        self.loop.run_until_complete(asyncio.wait([
            self.testvm1.start(),
            self.testvm2.start()]))

        self.loop.run_until_complete(self.testvm1.run_for_stdio(
            'cp /etc/passwd /tmp/passwd'))
        with self.qrexec_policy('qubes.Filecopy', self.testvm1, self.testvm2):
            try:
                self.loop.run_until_complete(
                    self.testvm1.run_for_stdio(
                        'qvm-copy-to-vm {} /tmp/passwd'.format(
                            self.testvm2.name)))
            except subprocess.CalledProcessError as e:
                self.fail('qvm-copy-to-vm failed: {}'.format(e.stderr))

        try:
            self.loop.run_until_complete(self.testvm2.run_for_stdio(
                'diff /etc/passwd /home/user/QubesIncoming/{}/passwd'.format(
                    self.testvm1.name)))
        except subprocess.CalledProcessError:
            self.fail('file differs')

        try:
            self.loop.run_until_complete(self.testvm1.run_for_stdio(
                'test -f /tmp/passwd'))
        except subprocess.CalledProcessError:
            self.fail('source file got removed')

    def test_105_qrexec_filemove(self):
        self.loop.run_until_complete(asyncio.wait([
            self.testvm1.start(),
            self.testvm2.start()]))

        self.loop.run_until_complete(self.testvm1.run_for_stdio(
            'cp /etc/passwd /tmp/passwd'))
        with self.qrexec_policy('qubes.Filecopy', self.testvm1, self.testvm2):
            try:
                self.loop.run_until_complete(
                    self.testvm1.run_for_stdio(
                        'qvm-move-to-vm {} /tmp/passwd'.format(
                            self.testvm2.name)))
            except subprocess.CalledProcessError as e:
                self.fail('qvm-move-to-vm failed: {}'.format(e.stderr))

        try:
            self.loop.run_until_complete(self.testvm2.run_for_stdio(
                'diff /etc/passwd /home/user/QubesIncoming/{}/passwd'.format(
                    self.testvm1.name)))
        except subprocess.CalledProcessError:
            self.fail('file differs')

        with self.assertRaises(subprocess.CalledProcessError):
            self.loop.run_until_complete(self.testvm1.run_for_stdio(
                'test -f /tmp/passwd'))

    def test_101_qrexec_filecopy_with_autostart(self):
        self.loop.run_until_complete(self.testvm1.start())

        with self.qrexec_policy('qubes.Filecopy', self.testvm1, self.testvm2):
            try:
                self.loop.run_until_complete(
                    self.testvm1.run_for_stdio(
                        'qvm-copy-to-vm {} /etc/passwd'.format(
                            self.testvm2.name)))
            except subprocess.CalledProcessError as e:
                self.fail('qvm-copy-to-vm failed: {}'.format(e.stderr))

        # workaround for libvirt bug (domain ID isn't updated when is started
        #  from other application) - details in
        # QubesOS/qubes-core-libvirt@63ede4dfb4485c4161dd6a2cc809e8fb45ca664f
        # XXX is it still true with qubesd? --woju 20170523
        self.testvm2._libvirt_domain = None
        self.assertTrue(self.testvm2.is_running())

        try:
            self.loop.run_until_complete(self.testvm2.run_for_stdio(
                'diff /etc/passwd /home/user/QubesIncoming/{}/passwd'.format(
                    self.testvm1.name)))
        except subprocess.CalledProcessError:
            self.fail('file differs')

        try:
            self.loop.run_until_complete(self.testvm1.run_for_stdio(
                'test -f /etc/passwd'))
        except subprocess.CalledProcessError:
            self.fail('source file got removed')

    def test_110_qrexec_filecopy_deny(self):
        self.loop.run_until_complete(asyncio.wait([
            self.testvm1.start(),
            self.testvm2.start()]))

        with self.qrexec_policy('qubes.Filecopy', self.testvm1, self.testvm2,
                allow=False):
            with self.assertRaises(subprocess.CalledProcessError):
                self.loop.run_until_complete(
                    self.testvm1.run_for_stdio(
                        'qvm-copy-to-vm {} /etc/passwd'.format(
                            self.testvm2.name)))

        with self.assertRaises(subprocess.CalledProcessError):
            self.loop.run_until_complete(self.testvm1.run_for_stdio(
                'test -d /home/user/QubesIncoming/{}'.format(
                    self.testvm1.name)))

    def test_115_qrexec_filecopy_no_agent(self):
        # The operation should not hang when qrexec-agent is down on target
        # machine, see QubesOS/qubes-issues#5347.

        self.loop.run_until_complete(asyncio.wait([
            self.testvm1.start(),
            self.testvm2.start()]))

        with self.qrexec_policy('qubes.Filecopy', self.testvm1, self.testvm2):
            try:
                self.loop.run_until_complete(
                    self.testvm2.run_for_stdio(
                        'systemctl stop qubes-qrexec-agent.service', user='root'))
            except subprocess.CalledProcessError:
                # A failure is normal here, because we're killing the qrexec
                # process that is handling the command.
                pass

            with self.assertRaises(subprocess.CalledProcessError):
                self.loop.run_until_complete(
                    asyncio.wait_for(
                        self.testvm1.run_for_stdio(
                            'qvm-copy-to-vm {} /etc/passwd'.format(
                                self.testvm2.name)),
                        timeout=30))

    @unittest.skip("Xen gntalloc driver crashes when page is mapped in the "
                   "same domain")
    def test_120_qrexec_filecopy_self(self):
        self.testvm1.start()
        self.qrexec_policy('qubes.Filecopy', self.testvm1.name,
            self.testvm1.name)
        p = self.testvm1.run("qvm-copy-to-vm %s /etc/passwd" %
                             self.testvm1.name, passio_popen=True,
                             passio_stderr=True)
        p.wait()
        self.assertEqual(p.returncode, 0, "qvm-copy-to-vm failed: %s" %
                         p.stderr.read())
        retcode = self.testvm1.run(
            "diff /etc/passwd /home/user/QubesIncoming/{}/passwd".format(
                self.testvm1.name),
            wait=True)
        self.assertEqual(retcode, 0, "file differs")

    @unittest.skipUnless(spawn.find_executable('xdotool'),
                         "xdotool not installed")
    def test_130_qrexec_filemove_disk_full(self):
        self.loop.run_until_complete(asyncio.wait([
            self.testvm1.start(),
            self.testvm2.start()]))

        self.loop.run_until_complete(self.wait_for_session(self.testvm1))

        # Prepare test file
        self.loop.run_until_complete(self.testvm1.run_for_stdio(
            'yes teststring | dd of=/tmp/testfile bs=1M count=50 '
            'iflag=fullblock'))

        # Prepare target directory with limited size
        self.loop.run_until_complete(self.testvm2.run_for_stdio(
            'mkdir -p /home/user/QubesIncoming && '
            'chown user /home/user/QubesIncoming && '
            'mount -t tmpfs none /home/user/QubesIncoming -o size=48M',
            user='root'))

        with self.qrexec_policy('qubes.Filecopy', self.testvm1, self.testvm2):
            p = self.loop.run_until_complete(self.testvm1.run(
                'qvm-move-to-vm {} /tmp/testfile'.format(
                    self.testvm2.name)))

            # Close GUI error message
            try:
                self.enter_keys_in_window('Error', ['Return'])
            except subprocess.CalledProcessError:
                pass
            self.loop.run_until_complete(p.wait())
            self.assertNotEqual(p.returncode, 0)

        # the file shouldn't be removed in source vm
        self.loop.run_until_complete(self.testvm1.run_for_stdio(
            'test -f /tmp/testfile'))

    def test_200_timezone(self):
        """Test whether timezone setting is properly propagated to the VM"""
        if "whonix" in self.template:
            self.skipTest("Timezone propagation disabled on Whonix templates")

        self.loop.run_until_complete(self.testvm1.start())
        vm_tz, _ = self.loop.run_until_complete(self.testvm1.run_for_stdio(
            'date +%Z'))
        dom0_tz = subprocess.check_output(['date', '+%Z'])
        self.assertEqual(vm_tz.strip(), dom0_tz.strip())

        # Check if reverting back to UTC works
        vm_tz, _ = self.loop.run_until_complete(self.testvm1.run_for_stdio(
            'TZ=UTC date +%Z'))
        self.assertEqual(vm_tz.strip(), b'UTC')

    def test_210_time_sync(self):
        """Test time synchronization mechanism"""
        if self.template.startswith('whonix-'):
            self.skipTest('qvm-sync-clock disabled for Whonix VMs')
        self.loop.run_until_complete(asyncio.wait([
            self.testvm1.start(),
            self.testvm2.start(),]))
        start_time = subprocess.check_output(['date', '-u', '+%s'])

        try:
            self.app.clockvm = self.testvm1
            self.app.save()
            # break vm and dom0 time, to check if qvm-sync-clock would fix it
            subprocess.check_call(['sudo', 'date', '-s', '2001-01-01T12:34:56'],
                stdout=subprocess.DEVNULL)
            self.loop.run_until_complete(
                self.testvm2.run_for_stdio('date -s 2001-01-01T12:34:56',
                    user='root'))

            self.loop.run_until_complete(
                self.testvm2.run_for_stdio('qvm-sync-clock',
                    user='root'))

            p = self.loop.run_until_complete(
                asyncio.create_subprocess_exec('sudo', 'qvm-sync-clock',
                    stdout=asyncio.subprocess.DEVNULL))
            self.loop.run_until_complete(p.wait())
            self.assertEqual(p.returncode, 0)
            vm_time, _ = self.loop.run_until_complete(
                self.testvm2.run_for_stdio('date -u +%s'))
            self.assertAlmostEquals(int(vm_time), int(start_time), delta=30)

            dom0_time = subprocess.check_output(['date', '-u', '+%s'])
            self.assertAlmostEquals(int(dom0_time), int(start_time), delta=30)

        except:
            # reset time to some approximation of the real time
            subprocess.Popen(
                ["sudo", "date", "-u", "-s", "@" + start_time.decode()])
            raise
        finally:
            self.app.clockvm = None

    def wait_for_pulseaudio_startup(self, vm):
        self.loop.run_until_complete(
            self.wait_for_session(self.testvm1))
        try:
            self.loop.run_until_complete(vm.run_for_stdio(
                "timeout 30s sh -c 'while ! pactl info; do sleep 1; done'"
            ))
        except subprocess.CalledProcessError as e:
            self.fail('Timeout waiting for pulseaudio start in {}: {}{}'.format(
                vm.name, e.stdout, e.stderr))
        # then wait for the stream to appear in dom0
        local_user = grp.getgrnam('qubes').gr_mem[0]
        p = self.loop.run_until_complete(asyncio.create_subprocess_shell(
            "sudo -E -u {} timeout 30s sh -c '"
            "while ! pactl list sink-inputs | grep -q :{}; do sleep 1; done'".format(
                local_user, vm.name)))
        self.loop.run_until_complete(p.wait())
        # and some more...
        self.loop.run_until_complete(asyncio.sleep(1))


    @unittest.skipUnless(spawn.find_executable('parecord'),
                         "pulseaudio-utils not installed in dom0")
    def test_220_audio_playback(self):
        if 'whonix-gw' in self.template:
            self.skipTest('whonix-gw have no audio')
        self.loop.run_until_complete(self.testvm1.start())
        try:
            self.loop.run_until_complete(
                self.testvm1.run_for_stdio('which parecord'))
        except subprocess.CalledProcessError:
            self.skipTest('pulseaudio-utils not installed in VM')

        self.wait_for_pulseaudio_startup(self.testvm1)
        # generate some "audio" data
        audio_in = b'\x20' * 44100
        self.loop.run_until_complete(
            self.testvm1.run_for_stdio('cat > audio_in.raw', input=audio_in))
        local_user = grp.getgrnam('qubes').gr_mem[0]
        with tempfile.NamedTemporaryFile() as recorded_audio:
            os.chmod(recorded_audio.name, 0o666)
            # FIXME: -d 0 assumes only one audio device
            p = subprocess.Popen(['sudo', '-E', '-u', local_user,
                'parecord', '-d', '0', '--raw', recorded_audio.name],
                stdout=subprocess.PIPE)
            try:
                self.loop.run_until_complete(
                    self.testvm1.run_for_stdio('paplay --raw audio_in.raw'))
            except subprocess.CalledProcessError as err:
                self.fail('{} stderr: {}'.format(str(err), err.stderr))
            # wait for possible parecord buffering
            self.loop.run_until_complete(asyncio.sleep(1))
            p.terminate()
            # for some reason sudo do not relay SIGTERM sent above
            subprocess.check_call(['pkill', 'parecord'])
            p.wait()
            # allow up to 20ms missing, don't use assertIn, to avoid printing
            # the whole data in error message
            recorded_audio = recorded_audio.file.read()
            if audio_in[:-3528] not in recorded_audio:
                found_bytes = recorded_audio.count(audio_in[0])
                all_bytes = len(audio_in)
                self.fail('played sound not found in dom0, '
                          'missing {} bytes out of {}'.format(
                              all_bytes-found_bytes, all_bytes))

    def _configure_audio_recording(self, vm):
        '''Connect VM's output-source to sink monitor instead of mic'''
        local_user = grp.getgrnam('qubes').gr_mem[0]
        sudo = ['sudo', '-E', '-u', local_user]
        source_outputs = subprocess.check_output(
            sudo + ['pacmd', 'list-source-outputs']).decode()

        last_index = None
        found = False
        for line in source_outputs.splitlines():
            if line.startswith('    index: '):
                last_index = line.split(':')[1].strip()
            elif line.startswith('\t\tapplication.name = '):
                app_name = line.split('=')[1].strip('" ')
                if vm.name == app_name:
                    found = True
                    break
        if not found:
            self.fail('source-output for VM {} not found'.format(vm.name))

        subprocess.check_call(sudo +
            ['pacmd', 'move-source-output', last_index, '0'])

    @unittest.skipUnless(spawn.find_executable('parecord'),
                         "pulseaudio-utils not installed in dom0")
    def test_221_audio_record_muted(self):
        if 'whonix-gw' in self.template:
            self.skipTest('whonix-gw have no audio')
        self.loop.run_until_complete(self.testvm1.start())
        try:
            self.loop.run_until_complete(
                self.testvm1.run_for_stdio('which parecord'))
        except subprocess.CalledProcessError:
            self.skipTest('pulseaudio-utils not installed in VM')

        self.wait_for_pulseaudio_startup(self.testvm1)
        # connect VM's recording source output monitor (instead of mic)
        self._configure_audio_recording(self.testvm1)

        # generate some "audio" data
        audio_in = b'\x20' * 44100
        local_user = grp.getgrnam('qubes').gr_mem[0]
        record = self.loop.run_until_complete(
            self.testvm1.run('parecord --raw audio_rec.raw'))
        # give it time to start recording
        self.loop.run_until_complete(asyncio.sleep(0.5))
        p = subprocess.Popen(['sudo', '-E', '-u', local_user,
            'paplay', '--raw'],
            stdin=subprocess.PIPE)
        p.communicate(audio_in)
        # wait for possible parecord buffering
        self.loop.run_until_complete(asyncio.sleep(1))
        self.loop.run_until_complete(
            self.testvm1.run_for_stdio('pkill parecord'))
        self.loop.run_until_complete(record.wait())
        recorded_audio, _ = self.loop.run_until_complete(
            self.testvm1.run_for_stdio('cat audio_rec.raw'))
        # should be empty or silence, so check just a little fragment
        if audio_in[:32] in recorded_audio:
            self.fail('VM recorded something, even though mic disabled')

    @unittest.skipUnless(spawn.find_executable('parecord'),
                         "pulseaudio-utils not installed in dom0")
    def test_222_audio_record_unmuted(self):
        if 'whonix-gw' in self.template:
            self.skipTest('whonix-gw have no audio')
        self.loop.run_until_complete(self.testvm1.start())
        try:
            self.loop.run_until_complete(
                self.testvm1.run_for_stdio('which parecord'))
        except subprocess.CalledProcessError:
            self.skipTest('pulseaudio-utils not installed in VM')

        self.wait_for_pulseaudio_startup(self.testvm1)
        da = qubes.devices.DeviceAssignment(self.app.domains[0], 'mic')
        self.loop.run_until_complete(
            self.testvm1.devices['mic'].attach(da))
        # connect VM's recording source output monitor (instead of mic)
        self._configure_audio_recording(self.testvm1)

        # generate some "audio" data
        audio_in = b'\x20' * 44100
        local_user = grp.getgrnam('qubes').gr_mem[0]
        record = self.loop.run_until_complete(
            self.testvm1.run('parecord --raw audio_rec.raw'))
        # give it time to start recording
        self.loop.run_until_complete(asyncio.sleep(0.5))
        p = subprocess.Popen(['sudo', '-E', '-u', local_user,
            'paplay', '--raw'],
            stdin=subprocess.PIPE)
        p.communicate(audio_in)
        # wait for possible parecord buffering
        self.loop.run_until_complete(asyncio.sleep(1))
        self.loop.run_until_complete(
            self.testvm1.run_for_stdio('pkill parecord || :'))
        _, record_stderr = self.loop.run_until_complete(record.communicate())
        if record_stderr:
            self.fail('parecord printed something on stderr: {}'.format(
                record_stderr))
        recorded_audio, _ = self.loop.run_until_complete(
            self.testvm1.run_for_stdio('cat audio_rec.raw'))
        # allow up to 20ms to be missing
        if audio_in[:-3528] not in recorded_audio:
            found_bytes = recorded_audio.count(audio_in[0])
            all_bytes = len(audio_in)
            self.fail('VM not recorded expected data, '
                      'missing {} bytes out of {}'.format(
                          all_bytes-found_bytes, all_bytes))

    def test_250_resize_private_img(self):
        """
        Test private.img resize, both offline and online
        :return:
        """
        # First offline test
        self.loop.run_until_complete(
            self.testvm1.storage.resize('private', 4*1024**3))
        self.loop.run_until_complete(self.testvm1.start())
        df_cmd = '( df --output=size /rw || df /rw | awk \'{print $2}\' )|' \
                 'tail -n 1'
        # new_size in 1k-blocks
        new_size, _ = self.loop.run_until_complete(
            self.testvm1.run_for_stdio(df_cmd))
        # some safety margin for FS metadata
        self.assertGreater(int(new_size.strip()), 3.8*1024**2)
        # Then online test
        self.loop.run_until_complete(
            self.testvm1.storage.resize('private', 6*1024**3))
        # new_size in 1k-blocks
        new_size, _ = self.loop.run_until_complete(
            self.testvm1.run_for_stdio(df_cmd))
        # some safety margin for FS metadata
        self.assertGreater(int(new_size.strip()), 5.7*1024**2)

    @unittest.skipUnless(spawn.find_executable('xdotool'),
                         "xdotool not installed")
    def test_300_bug_1028_gui_memory_pinning(self):
        """
        If VM window composition buffers are relocated in memory, GUI will
        still use old pointers and will display old pages
        :return:
        """

        # this test does too much asynchronous operations,
        # so let's rewrite it as a coroutine and call it as such
        return self.loop.run_until_complete(
            self._test_300_bug_1028_gui_memory_pinning())

    @asyncio.coroutine
    def _test_300_bug_1028_gui_memory_pinning(self):
        self.testvm1.memory = 800
        self.testvm1.maxmem = 800

        # exclude from memory balancing
        self.testvm1.features['service.meminfo-writer'] = False
        yield from self.testvm1.start()
        yield from self.wait_for_session(self.testvm1)

        # and allow large map count
        yield from self.testvm1.run('echo 256000 > /proc/sys/vm/max_map_count',
            user="root")

        allocator_c = '''
#include <sys/mman.h>
#include <stdlib.h>
#include <stdio.h>

int main(int argc, char **argv) {
    int total_pages;
    char *addr, *iter;

    total_pages = atoi(argv[1]);
    addr = mmap(NULL, total_pages * 0x1000, PROT_READ | PROT_WRITE,
        MAP_ANONYMOUS | MAP_PRIVATE | MAP_POPULATE, -1, 0);
    if (addr == MAP_FAILED) {
        perror("mmap");
        exit(1);
    }

    printf("Stage1\\n");
    fflush(stdout);
    getchar();
    for (iter = addr; iter < addr + total_pages*0x1000; iter += 0x2000) {
        if (mlock(iter, 0x1000) == -1) {
            perror("mlock");
            fprintf(stderr, "%d of %d\\n", (iter-addr)/0x1000, total_pages);
            exit(1);
        }
    }

    printf("Stage2\\n");
    fflush(stdout);
    for (iter = addr+0x1000; iter < addr + total_pages*0x1000; iter += 0x2000) {
        if (munmap(iter, 0x1000) == -1) {
            perror(\"munmap\");
            exit(1);
        }
    }

    printf("Stage3\\n");
    fflush(stdout);
    fclose(stdout);
    getchar();

    return 0;
}
'''

        yield from self.testvm1.run_for_stdio('cat > allocator.c',
            input=allocator_c.encode())

        try:
            yield from self.testvm1.run_for_stdio(
                'gcc allocator.c -o allocator')
        except subprocess.CalledProcessError as e:
            self.skipTest('allocator compile failed: {}'.format(e.stderr))

        # drop caches to have even more memory pressure
        yield from self.testvm1.run_for_stdio(
            'echo 3 > /proc/sys/vm/drop_caches', user='root')

        # now fragment all free memory
        stdout, _ = yield from self.testvm1.run_for_stdio(
            "grep ^MemFree: /proc/meminfo|awk '{print $2}'")
        memory_pages = int(stdout) // 4  # 4k pages

        alloc1 = yield from self.testvm1.run(
            'ulimit -l unlimited; exec /home/user/allocator {}'.format(
                memory_pages),
            user="root",
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

        # wait for memory being allocated; can't use just .read(), because EOF
        # passing is unreliable while the process is still running
        alloc1.stdin.write(b'\n')
        yield from alloc1.stdin.drain()
        try:
            alloc_out = yield from alloc1.stdout.readexactly(
                len('Stage1\nStage2\nStage3\n'))
        except asyncio.IncompleteReadError as e:
            alloc_out = e.partial

        if b'Stage3' not in alloc_out:
            # read stderr only in case of failed assert (), but still have nice
            # failure message (don't use self.fail() directly)
            #
            # stderr isn't always read, because on not-failed run, the process
            # is still running, so stderr.read() will wait (indefinitely).
            self.assertIn(b'Stage3', alloc_out,
                (yield from alloc1.stderr.read()))

        # now, launch some window - it should get fragmented composition buffer
        # it is important to have some changing content there, to generate
        # content update events (aka damage notify)
        proc = yield from self.testvm1.run(
            'xterm -maximized -e top')

        if proc.returncode is not None:
            self.fail('xterm failed to start')
        # get window ID
        winid = yield from self.wait_for_window_coro(
            self.testvm1.name + ':xterm',
            search_class=True)
        xprop = yield from asyncio.get_event_loop().run_in_executor(None,
            subprocess.check_output,
            ['xprop', '-notype', '-id', winid, '_QUBES_VMWINDOWID'])
        vm_winid = xprop.decode().strip().split(' ')[4]

        # now free the fragmented memory and trigger compaction
        alloc1.stdin.write(b'\n')
        yield from alloc1.stdin.drain()
        yield from alloc1.wait()
        yield from self.testvm1.run_for_stdio(
            'echo 1 > /proc/sys/vm/compact_memory', user='root')

        # now window may be already "broken"; to be sure, allocate (=zero)
        # some memory
        alloc2 = yield from self.testvm1.run(
            'ulimit -l unlimited; /home/user/allocator {}'.format(memory_pages),
            user='root', stdout=subprocess.PIPE)
        yield from alloc2.stdout.read(len('Stage1\n'))

        # wait for damage notify - top updates every 3 sec by default
        yield from asyncio.sleep(6)

        # stop changing the window content
        subprocess.check_call(['xdotool', 'key', '--window', winid, 'd'])

        # now take screenshot of the window, from dom0 and VM
        # choose pnm format, as it doesn't have any useless metadata - easy
        # to compare
        vm_image, _ = yield from self.testvm1.run_for_stdio(
            'import -window {} pnm:-'.format(vm_winid))

        dom0_image = yield from asyncio.get_event_loop().run_in_executor(None,
            subprocess.check_output, ['import', '-window', winid, 'pnm:-'])

        if vm_image != dom0_image:
            self.fail("Dom0 window doesn't match VM window content")

class TC_10_Generic(qubes.tests.SystemTestCase):
    def setUp(self):
        super(TC_10_Generic, self).setUp()
        self.init_default_template()
        self.vm = self.app.add_new_vm(
            qubes.vm.appvm.AppVM,
            name=self.make_vm_name('vm'),
            label='red',
            template=self.app.default_template)
        self.loop.run_until_complete(self.vm.create_on_disk())
        self.app.save()
        self.vm = self.app.domains[self.vm.qid]

    def test_000_anyvm_deny_dom0(self):
        '''$anyvm in policy should not match dom0'''
        policy = open("/etc/qubes-rpc/policy/test.AnyvmDeny", "w")
        policy.write("%s $anyvm allow" % (self.vm.name,))
        policy.close()
        self.addCleanup(os.unlink, "/etc/qubes-rpc/policy/test.AnyvmDeny")

        flagfile = '/tmp/test-anyvmdeny-flag'
        if os.path.exists(flagfile):
            os.remove(flagfile)

        self.create_local_file('/etc/qubes-rpc/test.AnyvmDeny',
            'touch {}\necho service output\n'.format(flagfile))

        self.loop.run_until_complete(self.vm.start())
        with self.qrexec_policy('test.AnyvmDeny', self.vm, '$anyvm'):
            with self.assertRaises(subprocess.CalledProcessError,
                    msg='$anyvm matched dom0') as e:
                self.loop.run_until_complete(
                    self.vm.run_for_stdio(
                        '/usr/lib/qubes/qrexec-client-vm dom0 test.AnyvmDeny'))
            stdout = e.exception.output
            stderr = e.exception.stderr
        self.assertFalse(os.path.exists(flagfile),
            'Flag file created (service was run) even though should be denied,'
            ' qrexec-client-vm output: {} {}'.format(stdout, stderr))

def create_testcases_for_templates():
    return qubes.tests.create_testcases_for_templates('TC_00_AppVM',
        TC_00_AppVMMixin, qubes.tests.SystemTestCase,
        module=sys.modules[__name__])

def load_tests(loader, tests, pattern):
    tests.addTests(loader.loadTestsFromNames(
        create_testcases_for_templates()))
    return tests

qubes.tests.maybe_create_testcases_on_import(create_testcases_for_templates)
