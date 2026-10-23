"""External filesystem changes, view identity, async races and monitor cleanup."""
import os
from pathlib import Path
import select
import tempfile
import threading
import time

import harness as H
from apps.filemgr import FileWindow
from accessibility import Tree
from directory_listing import scan, parse_launcher
from directory_monitor import DirectoryMonitor


def labels(grid): return [item['label'] for item in grid.items]
def pump(monitor):
    if select.select([monitor.notify_r], [], [], 0)[0]: monitor.read()
    monitor.tick(time.time())
def wait(monitor, check, reason, seconds=4):
    end = time.monotonic()+seconds
    while time.monotonic()<end:
        pump(monitor)
        if check(): return
        time.sleep(.01)
    raise AssertionError(reason)
def close(monitor):
    monitor.close()
    for thread in monitor.threads: thread.join(timeout=1)
    assert not any(thread.is_alive() for thread in monitor.threads)


with H.desktop_dir() as dd:
    root=Path(dd); (root/'keep.txt').write_text('keep')
    d=H.make_desk(); win=FileWindow(d,dd); d.wm.add(win)
    tree=Tree(d); tree.build()
    item=next(item for item in d.shell.grid.items if item['label']=='keep.txt')
    i=d.shell.grid.items.index(item)
    d.shell.grid.sel={i};d.shell.grid._keyboard_item=d.shell.grid._selection_anchor=i
    before=tree.item_ids(d.shell.grid,d.shell.grid.items)[i]
    monitor=DirectoryMonitor(d)
    try:
        win.addr.set('/unfinished address draft')
        win.addr.cur = 5
        (root/'added.txt').write_text('outside the desktop')
        wait(monitor,lambda:'added.txt' in labels(d.shell.grid) and 'added.txt' in labels(win.grid),'External create did not reach both live views')
        assert d.shell.grid.selected_items()==[item]
        assert d.shell.grid.items[d.shell.grid._keyboard_item] is item
        assert tree.item_ids(d.shell.grid,d.shell.grid.items)[d.shell.grid.items.index(item)]==before
        assert win.addr.text == '/unfinished address draft' and win.addr.cur == 5
        (root/'added.txt').rename(root/'renamed.txt')
        wait(monitor,lambda:'renamed.txt' in labels(d.shell.grid) and 'added.txt' not in labels(win.grid),'External rename did not refresh')
        (root/'renamed.txt').unlink()
        wait(monitor,lambda:'renamed.txt' not in labels(d.shell.grid) and 'renamed.txt' not in labels(win.grid),'External delete did not refresh')

        # Launcher edits update displayed labels without running the command.
        launcher=root/'outside.desktop'
        launcher.write_text('[Desktop Entry]\nName=First external\nExec=does-not-run\n')
        wait(monitor,lambda:'First external' in labels(d.shell.grid),'External launcher did not appear')
        launcher.write_text('[Desktop Entry]\nName=Second external\nExec=still-does-not-run\n')
        wait(monitor,lambda:'Second external' in labels(d.shell.grid) and 'First external' not in labels(win.grid),'Launcher content edit remained stale')

        # Menus/captured drags freeze rows until input has completed.
        d.mouse_owner=lambda ev:None
        (root/'held.txt').write_text('held')
        end=time.monotonic()+.4
        while time.monotonic()<end: pump(monitor);time.sleep(.01)
        assert 'held.txt' not in labels(d.shell.grid)
        d.mouse_owner=None
        wait(monitor,lambda:'held.txt' in labels(d.shell.grid),'Deferred rows did not resume after drag release')

        # A replacement cannot inherit an old activation, even before refresh.
        old_item=next(item for item in d.shell.grid.items if item['label']=='keep.txt')
        old_key=tree.item_ids(d.shell.grid,d.shell.grid.items)[d.shell.grid.items.index(old_item)]
        replacement=root/'replacement.tmp';replacement.write_text('replacement')
        os.replace(replacement,root/'keep.txt')
        opened=[];original=d.shell.open_path;d.shell.open_path=opened.append
        assert tree.apply(old_key,'activate',[]) is False and not opened
        d.shell.open_path=original
        tree.build();assert not tree.apply(old_key,'activate',[])
        wait(monitor,lambda:'keep.txt' in labels(win.grid),'Replacement was not displayed')

        # Removing a viewed folder produces an empty view, not repeated modals;
        # recreating the path is detected through its parent watch.
        parent=root/'parent';parent.mkdir();view=parent/'view';view.mkdir()
        other=FileWindow(d,str(view));d.wm.add(other);pump(monitor)
        (view/'initial.txt').write_text('initial')
        wait(monitor,lambda:'initial.txt' in labels(other.grid),'Newly opened view was not watched')
        (view/'initial.txt').unlink();view.rmdir()
        wait(monitor,lambda:other.listing_error is not None and not other.grid.items,'Deleted folder remained stale')
        assert d.wm.modal_top() is None
        d.render();tree.build()
        assert any(node['name']=='Folder unavailable' and node['role']=='status bar' for node in tree.nodes.values())
        view.mkdir();(view/'returned.txt').write_text('returned')
        wait(monitor,lambda:'returned.txt' in labels(other.grid) and other.listing_error is None,'Recreated directory did not rearm')
    finally: close(monitor)
    assert monitor.notify_r not in d.fd_hooks and monitor.tick not in d.tick_hooks
    monitor.close()  # Shutdown remains idempotent.


# Slow scans cannot block UI callbacks, another view, navigation, or shutdown.
with H.desktop_dir() as dd, tempfile.TemporaryDirectory() as outside:
    d=H.make_desk(); win=FileWindow(d,outside);d.wm.add(win)
    entered,release=threading.Event(),threading.Event()
    def slow(path):
        if path==outside:
            entered.set();release.wait(timeout=4)
        return scan(path)
    monitor=DirectoryMonitor(d,scanner=slow,interval=.3)
    try:
        assert entered.wait(timeout=2)
        (Path(dd)/'responsive.txt').write_text('desktop remains responsive')
        wait(monitor,lambda:'responsive.txt' in labels(d.shell.grid),'A blocked scan held up another directory')
        win.navigate(dd);pump(monitor)
        release.set()
        wait(monitor,lambda:'responsive.txt' in labels(win.grid),'Navigation did not receive its current directory')
        assert win.path==dd and 'responsive.txt' in labels(win.grid)
    finally:
        release.set();close(monitor)


# No notifications available: periodic worker snapshots remain functional.
import directory_monitor as module
native=module.Inotify
def unavailable(paths): raise OSError('Unavailable in this controlled fallback test')
module.Inotify=unavailable
with H.desktop_dir() as dd:
    d=H.make_desk();monitor=DirectoryMonitor(d,interval=.2)
    try:
        (Path(dd)/'fallback.txt').write_text('fallback')
        wait(monitor,lambda:'fallback.txt' in labels(d.shell.grid),'Fallback consistency scan did not refresh')
    finally: close(monitor)
module.Inotify=native

# Healthy notifications need no periodic rescans of every open folder (network
# mounts included); an incomplete watch set still falls back to them.
def count_scans(backend_type, seconds=1.2, table=None, slow_interval=60):
    module.Inotify=backend_type
    try:
        with H.desktop_dir() as dd:
            if table is not None:
                module.mount_table=lambda: table(os.path.realpath(dd))
            d=H.make_desk();calls=[]
            def counting(path):
                calls.append(time.monotonic());return scan(path)
            monitor=DirectoryMonitor(d,scanner=counting,interval=.2,slow_interval=slow_interval)
            try:
                wait(monitor,lambda:bool(calls),'Initial snapshot was not taken')
                start=time.monotonic()
                while time.monotonic()-start<seconds: pump(monitor);time.sleep(.02)
                quiet=[t for t in calls if t>=start]
                (Path(dd)/'after.txt').write_text('event-driven')
                wait(monitor,lambda:'after.txt' in labels(d.shell.grid),'Change after a quiet period was missed')
                return len(quiet)
            finally: close(monitor)
    finally: module.Inotify=native;module.mount_table=native_table
native_table=module.mount_table
class Incomplete(native):
    def __init__(self,paths):
        super().__init__(paths);self.complete=False
assert count_scans(native)==0, 'Healthy inotify still rescanned periodically'
assert count_scans(Incomplete)>=3, 'An incomplete watch set lost its periodic fallback'

# Review D S2: inotify watches succeed on NFS, SMB and FUSE mounts but never
# report other clients' changes, so those views keep a slow periodic rescan.
# A local view stays event-driven even with the same short slow interval.
local=lambda view:[('/','ext4')]
for remote in ('nfs4','cifs','smb3','fuse.sshfs','sshfs'):
    table=lambda view,remote=remote:[('/','ext4'),(view,remote)]
    assert count_scans(native,table=table,slow_interval=.2)>=3, remote+' view was not rescanned'
assert count_scans(native,table=local,slow_interval=.2)==0, 'A local view was rescanned periodically'
with tempfile.TemporaryDirectory() as tmp:
    mountinfo=Path(tmp)/'mountinfo'
    mountinfo.write_text(
        '22 1 8:2 / / rw,relatime shared:1 - ext4 /dev/sda2 rw\n'
        '30 22 0:40 / /mnt/my\\040share rw - cifs //srv/share rw\n'
        '31 22 0:41 / /srv/remote rw shared:9 master:2 - fuse.sshfs u@h: rw\n'
        '32 22 0:42 / /srv/remote/over rw - tmpfs tmpfs rw\n'
        '33 22 0:43 / /mnt/disk rw - fuseblk /dev/sdb1 rw\n')
    rows=module.mount_table(str(mountinfo))
    assert ('/mnt/my share','cifs') in rows, rows
    kinds={path:module.filesystem_type(path,rows) for path in
           ('/home','/mnt/my share/docs','/mnt/my','/srv/remote/a','/srv/remote/over/b','/mnt/disk/c')}
    assert kinds=={'/home':'ext4','/mnt/my share/docs':'cifs','/mnt/my':'ext4',
                   '/srv/remote/a':'fuse.sshfs','/srv/remote/over/b':'tmpfs',
                   '/mnt/disk/c':'fuseblk'}, kinds
    assert [module.remote_filesystem(kinds[p]) for p in sorted(kinds)]==[
        False,False,False,True,True,False], sorted(kinds)

# Renaming a grandparent moves no watched inode: the ancestor watches notice
# it (and its return) without any periodic scan.
with H.desktop_dir() as dd, tempfile.TemporaryDirectory() as outside:
    base=Path(outside);view=base/'a'/'b'/'c';view.mkdir(parents=True)
    (view/'deep.txt').write_text('deep')
    d=H.make_desk();win=FileWindow(d,str(view));d.wm.add(win)
    monitor=DirectoryMonitor(d,interval=60,slow_interval=60)
    try:
        wait(monitor,lambda:'deep.txt' in labels(win.grid),'Initial deep view was not listed')
        # Let the start-up snapshots settle so no scan is already queued.
        quiet=time.monotonic()+.6
        while time.monotonic()<quiet:
            pump(monitor);time.sleep(.01)
            if monitor.deadlines or monitor.busy: quiet=time.monotonic()+.6
        (base/'a').rename(base/'moved')
        wait(monitor,lambda:win.listing_error is not None and not win.grid.items,'A renamed grandparent left the view stale')
        (base/'moved').rename(base/'a')
        wait(monitor,lambda:'deep.txt' in labels(win.grid) and win.listing_error is None,'A restored grandparent did not rearm the view')
    finally: close(monitor)

# A queue overflow must invalidate every displayed folder and rearm watches.
reader,writer=os.pipe2(os.O_NONBLOCK|os.O_CLOEXEC)
backend=module.Inotify.__new__(module.Inotify)
backend.fd,backend.paths=reader,{}
try:
    os.write(writer,module.EVENT.pack(-1,0x4000,0,0))
    changed,rearm=backend.changes({'/first','/second'})
    assert changed=={'/first','/second'} and rearm
finally:
    backend.close();os.close(writer)

# Special launcher entries are never consumed as blocking input streams.
with tempfile.TemporaryDirectory() as tmp:
    pipe=Path(tmp)/'pipe.desktop';os.mkfifo(pipe)
    assert parse_launcher(pipe)=={}
print('Directory monitoring, live identity, async navigation and cleanup checks passed.')
