"""Vector's driving tricks, done with his real motion commands (a regular Vector ignores the 'intents'
WirePod sends for these, which is why Fetch cube etc. used to do nothing).

  fetch_cube     find the cube, pick it up, bring it to you (or set it down where he is)
  roll_cube      find the cube and roll it
  pop_a_wheelie  wheelie off the cube
  come_here      find your face and drive toward you
  explore        roam the mapped desk (asks for a desk scan first if there is no map)
  dance          a dance animation (wheels allowed)
  go_to_charger  back to the dock
  desk_scan      map the desk (edges, obstacles, the floor in between), starting and ending on the dock
  roam           wander the mapped desk: planned paths, never off the map, back to the dock at the end
  stop_moving    stop whatever driving he's doing

Each runs in the background and talks: "On it." / what went wrong. All are refused while the dock
lock is on. Cliff and obstacle safety: his own firmware stops actions at cliffs; short hops only.
"""
from __future__ import annotations

import random
import threading
import time

from . import face_art, settings as S

HUD_TITLES = {"fetch_cube": "TARGET: CUBE", "roll_cube": "TARGET: CUBE", "pop_a_wheelie": "MANEUVER",
              "come_here": "APPROACH", "look_at_me": "TRACKING", "explore": "PATROL", "roam": "PATROL",
              "desk_scan": "MAPPING DESK", "go_to_charger": "DOCKING"}

ACTIONS = ("fetch_cube", "roll_cube", "pop_a_wheelie", "come_here", "explore", "dance", "go_to_charger",
           "desk_scan", "roam", "stop_moving")


def _jarvis() -> bool:
    return S.load().get("persona", {}).get("style") == "jarvis"


def _deg(d):
    from anki_vector.util import degrees
    return degrees(d)


def _mm(d):
    from anki_vector.util import distance_mm
    return distance_mm(d)


def _degps(d):
    from anki_vector.util import degrees
    return degrees(d)


def _speed(s):
    from anki_vector.util import speed_mmps
    return speed_mmps(s)


class Motion:
    def __init__(self, comp):
        self.c = comp
        self.busy = None
        self.lock = threading.Lock()
        self.cancel = threading.Event()

    def stop(self) -> dict:
        was = self.busy
        self.cancel.set()
        try:
            self.c.drive_cmd = {"lw": 0.0, "rw": 0.0, "at": time.time()}
        except Exception:  # noqa: BLE001
            pass
        return {"stopped": was}

    # ------------------------------------------------------------ entry
    def start(self, action: str) -> dict:
        if action == "stop_moving":
            return self.stop()
        if S.load()["safety"].get("dock_lock") and action not in ("dance", "look_at_me"):  # those stay on the dock
            raise PermissionError("The dock lock is on. Turn it off (Drive & Camera or Robot Settings) to let him drive.")
        if not self.lock.acquire(blocking=False):
            raise RuntimeError(f"He's still busy with {self.busy.replace('_', ' ')}.")
        self.busy = action
        self.step = ""
        self.cancel.clear()
        # the still-hold stays on: our commands outrank it, and dropping it made him lose control mid-move
        threading.Thread(target=self._run, args=(action,), daemon=True).start()
        threading.Thread(target=self._hud, args=(action,), daemon=True).start()
        return {"started": action}

    def _hud(self, action: str):
        """Jarvis mode: while he works, his face is a HUD (radar, task, progress), never Vector's eyes."""
        from . import deskmap
        k = 0
        time.sleep(0.5)
        while self.busy == action:
            if _jarvis() and time.time() >= self.c.speaking_until and action != "dance":
                p = deskmap.get().progress
                sub = (p or {}).get("step") or self.step or "in progress"
                img = face_art.hud_action(HUD_TITLES.get(action, action.replace("_", " ")), sub, phase=(k % 8) / 8)
                r = self.c.raw
                try:
                    self.c.call(lambda: self.c.put_screen(r, img, 3), 5, "hud")
                except Exception:  # noqa: BLE001
                    pass
            k += 1
            time.sleep(4.0)  # each frame is ~35 KB over his Wi-Fi: don't crowd out the driving commands

    def _run(self, action: str):
        from .companion import log
        log(f"motion: {action}")
        from . import deskmap
        try:
            getattr(self, action)()
        except InterruptedError:
            log(f"motion: {action} stopped")
            self._say("Stopped, sir." if _jarvis() else "Okay, stopping.")
        except deskmap.Lost:
            log(f"motion: {action}: he was picked up")
            self._say("I've lost my place, sir. Put me on my charger and I'll get my bearings."
                      if _jarvis() else "Whoa! Put me back on my charger so I know where I am.")
        except Exception as e:  # noqa: BLE001
            msg = str(e) or e.__class__.__name__
            log(f"motion: {action} failed: {msg}")
            self._say(self._friendly(action, msg))
        finally:
            deskmap.get().progress = None
            self.c.motion_ended = time.time()
            self.c.cube_handled_until = time.time() + 5
            self.c.still_paused_until = 0  # the cube settling after he lets go isn't a tap
            self.busy = None
            self.lock.release()

    @staticmethod
    def _friendly(action, msg):
        m = msg.lower()
        if "pick up" in m:
            return ("I couldn't get a grip on the cube, sir. Put it on open, flat desk, away from the mat's edge."
                    if _jarvis() else "I couldn't pick up my cube. Put it somewhere flat and open!")
        if "cube" in m and ("not" in m or "find" in m or "no " in m):
            return "I can't find my cube. Put it in front of me and try again."
        if "charger" in m or "map" in m or "where i am" in m:
            return msg
        if "slow" in m or "time" in m:
            return "That took too long, so I stopped."
        return f"I couldn't {action.replace('_', ' ')} just now."

    # ------------------------------------------------------------ helpers
    def _say(self, text: str):
        try:
            self.c.say(text)
        except Exception:  # noqa: BLE001
            pass

    def _call(self, fn, timeout: float, name: str):
        return self.c.call(fn, timeout, name)

    def _off_dock(self, r):
        try:
            if r.status.is_on_charger:
                self._call(lambda: r.behavior.drive_off_charger(), 30, "drive_off_charger")
        except AttributeError:
            pass

    def _cube(self, r, search: bool = True):
        """The cube, looking for it (turning in place) if he can't see it yet. Works from what his camera
        sees, so it doesn't need the cube's Bluetooth link (that's only for lights and taps)."""
        from .companion import log
        cube = r.world.connected_light_cube
        if cube is None:
            try:
                self.c.cube_pool.submit(r.world.connect_cube).result(timeout=25)
                cube = r.world.connected_light_cube
            except Exception as e:  # noqa: BLE001
                log(f"motion: cube bluetooth not connected ({e.__class__.__name__}); finding it by sight")
        cube = cube or r.world._light_cube.get(next(iter(r.world._light_cube)))
        since = time.time() - 3

        def seen():
            # is_visible lapses about a second after the last sighting, so a glimpse mid-turn was missed;
            # any sighting since the search began counts
            t = getattr(cube, "last_observed_time", None) if cube else None
            return bool(cube and (cube.is_visible or (t and t > since)))
        log(f"motion: cube connected={bool(r.world.connected_light_cube)} visible={seen()} "
            f"on_charger={r.status.is_on_charger}")
        if seen() or not search:
            return cube
        self._call(lambda: r.behavior.set_lift_height(0.0), 10, "set_lift_height")
        for head in (-20, -5, 12):  # close, mid, far: the markers have to be in frame and in focus
            self._call(lambda: r.behavior.set_head_angle(_deg(head)), 10, "set_head_angle")
            for step in range(12):  # a full circle in 30-degree steps (45 skipped past it)
                time.sleep(0.9)
                if seen():
                    log(f"motion: cube spotted (head {head}, step {step})")
                    return cube
                self._call(lambda: r.behavior.turn_in_place(_deg(30), speed=_degps(90)), 15, "turn_in_place")
            if head == -20:  # maybe he's too close to it: back up a little and look again
                self._call(lambda: r.behavior.drive_straight(_mm(-80), _speed(60)), 15, "drive_straight")
        raise RuntimeError("couldn't find the cube")

    def _control(self):
        """(still in control?, take it back): lets desk driving notice when one of his reflexes took over."""
        c = self.c

        def regain():
            r = c.raw
            c.call(lambda: r.conn.request_control(timeout=6), 8, "request_control")
            c.ctl_held = True
        return c.has_control, regain

    def _safe_forward(self, r, mm: float):
        """Forward in short checked hops: stops for the desk edge, marked areas and anything in the way."""
        from . import deskmap
        m = deskmap.get()
        if not m.anchored(r):
            m.anchor_from_charger(r)
        if m.anchored(r):
            d = deskmap.Driver(m, r, self._call, self.cancel, print, *self._control())
            for _ in range(int(mm // 50)):
                if d.hop(50, speed=60) != "ok":
                    break
            return
        for _ in range(int(mm // 50)):  # no map position: still never blind
            p = r.proximity.last_sensor_reading
            if p is None or p.is_lift_in_fov or (p.found_object and p.distance.distance_mm < 130) or r.status.is_cliff_detected:
                break
            self._call(lambda: r.behavior.drive_straight(_mm(50), _speed(60), should_play_anim=False), 15, "drive_straight")
            if r.status.is_cliff_detected:
                self._call(lambda: r.behavior.drive_straight(_mm(-50), _speed(60), should_play_anim=False), 15, "drive_straight")
                break

    def _face_turn(self, r) -> bool:
        """Turn toward a face he can see (looking up and around for one). True if found."""
        self._call(lambda: r.behavior.set_head_angle(_deg(30)), 10, "set_head_angle")
        for _ in range(8):
            faces = list(r.world.visible_faces)
            if faces:
                self._call(lambda: r.behavior.turn_towards_face(faces[0]), 20, "turn_towards_face")
                return True
            self._call(lambda: r.behavior.turn_in_place(_deg(45)), 15, "turn_in_place")
            time.sleep(0.8)
        return False

    # ------------------------------------------------------------ actions
    def fetch_cube(self):
        from .companion import log
        with self.c.control():
            r = self.c.raw  # unwrapped: these calls get their own long time limits below
            self._say("Retrieving the cube, sir." if _jarvis() else "Fetching my cube.")
            self._off_dock(r)
            cube = self._cube(r)
            self.c.cube_color("blue")
            ok_ctl, regain = self._control()
            for attempt in (1, 2):
                try:
                    res = self._call(lambda: r.behavior.pickup_object(cube, num_retries=1), 90, "pickup_object")
                except Exception:  # noqa: BLE001
                    res = None
                if r.status.is_carrying_block:
                    break
                if not ok_ctl():  # one of his reflexes interrupted the pick-up: take back over and try once more
                    time.sleep(2.0)
                    regain()
                log(f"motion: pick-up attempt {attempt} didn't work ({getattr(res, 'result', res)})")
                if attempt == 2:
                    raise RuntimeError("couldn't pick up the cube")
                cube = self._cube(r)
            if self._face_turn(r):
                self._safe_forward(r, 150)
            self._call(lambda: r.behavior.place_object_on_ground_here(num_retries=1), 40, "place_object_on_ground_here")
            self.c.cube_color("green", 3)
        self._say("Here's your cube, sir." if _jarvis() else "Got it!")

    def roll_cube(self):
        with self.c.control():
            r = self.c.raw  # unwrapped: these calls get their own long time limits below
            self._off_dock(r)
            cube = self._cube(r)
            self._call(lambda: r.behavior.roll_cube(cube, num_retries=2), 60, "roll_cube")

    def pop_a_wheelie(self):
        with self.c.control():
            r = self.c.raw  # unwrapped: these calls get their own long time limits below
            self._off_dock(r)
            cube = self._cube(r)
            self._call(lambda: r.behavior.pop_a_wheelie(cube, num_retries=2), 60, "pop_a_wheelie")

    def look_at_me(self):
        with self.c.control():
            r = self.c.raw
            if not self._face_turn(r):
                self._say("I can't see you.")

    def come_here(self):
        with self.c.control():
            r = self.c.raw  # unwrapped: these calls get their own long time limits below
            self._off_dock(r)
            if not self._face_turn(r):
                self._say("I can't see you. Wave at me and try again.")
                return
            self._safe_forward(r, 200)
            self._call(lambda: r.behavior.set_head_angle(_deg(35)), 10, "set_head_angle")
        self._say("Here I am, sir." if _jarvis() else "Hi!")

    def explore(self):
        """Without a map he'd be driving blind, so explore = roam the mapped desk."""
        from . import deskmap
        if not deskmap.get().scanned:
            self._say("I haven't mapped the desk yet, sir. Say: scan the desk." if _jarvis()
                      else "I need to map my desk first. Say: scan the desk!")
            return
        self.roam()

    def desk_scan(self):
        from . import deskmap
        from .companion import log
        m = deskmap.get()
        self._say("Mapping the desk, sir. Please leave everything where it is; this takes about ten minutes."
                  if _jarvis() else "Ooh, let me explore my desk! This takes a few minutes.")
        with self.c.control():
            r = self.c.raw
            out = deskmap.scan(m, r, self._call, self.cancel, log=log, minutes=12, control=self._control())
        self.c.desk_changed()
        n = out["obstacles"]
        what = f"{n} thing{'s' if n != 1 else ''} to steer around" if n else "nothing in the way"
        self._say((f"Desk mapped, sir: about {out['area_m2']:.1f} square metres of driving room and {what}. "
                   "You can name things and mark keep-out areas in the app.") if _jarvis()
                  else f"All mapped! I found {what}.")

    def roam(self):
        from . import deskmap
        from .companion import log
        m = deskmap.get()

        def pause():  # a moment at each spot: look around like he's curious (Jarvis: just a glance)
            from anki_vector.util import degrees
            r = self.c.raw
            self._call(lambda: r.behavior.set_head_angle(degrees(random.choice([0, 15, 30]))), 10, "set_head_angle")
            time.sleep(1.0 if _jarvis() else 2.0)
        if not _jarvis():
            self._say("Exploring!")
        with self.c.control():
            r = self.c.raw
            out = deskmap.roam(m, r, self._call, self.cancel, log=log, minutes=3, pause=pause, control=self._control())
        log(f"motion: roam {out}")
        if not out.get("docked"):
            self._say("I couldn't get back on my charger, sir." if _jarvis() else "Help, I can't find my charger!")

    def dance(self):
        """A choreographed routine: head, lift and (off the dock) small turns, on the beat. Vector's own
        'dance' animations wait for music he can hear, which is why Dance used to hang and fail."""
        from anki_vector.util import degrees
        jarvis = _jarvis()
        self._say("Initiating routine, sir." if jarvis else "Let's dance!")
        beat = 0.42
        with self.c.control():
            r = self.c.raw
            docked = r.status.is_on_charger
            # motor speeds instead of 'move to' commands: each is fire-and-forget, so the beat holds even on
            # slow Wi-Fi (waiting for every move to report back made the routine drag)
            pattern = [(3, 4, 1), (-3, 4, -1), (3, -4, 1), (-3, -4, -1)] * 2 + [(3, 6, 2), (-3, -6, -2)] * 2 + \
                      [(2, 4, 1), (-2, -4, -1), (3, 5, 2), (-3, -5, -2)] * 2
            for i, (hd, lf, tw) in enumerate(pattern):
                if self.cancel.is_set():
                    break
                t0 = time.time()
                if (jarvis and i % 2 == 0) or i % 4 == 0:
                    img = face_art.equalizer(i / len(pattern) * 3, face_art.CYAN if jarvis else face_art.PINK)
                    try:
                        self._call(lambda: self.c.put_screen(r, img, beat * 4 + 0.5), 3, "hud")
                    except Exception:  # noqa: BLE001
                        pass
                self._call(lambda: r.motors.set_head_motor(hd), 3, "set_head_motor")
                self._call(lambda: r.motors.set_lift_motor(lf), 3, "set_lift_motor")
                if not docked:  # never spin his wheels on the charger
                    w = 70 * tw
                    self._call(lambda: r.motors.set_wheel_motors(w, -w), 3, "set_wheel_motors")
                time.sleep(max(0.0, beat - (time.time() - t0)))
            for fn in (lambda: r.motors.set_wheel_motors(0, 0), lambda: r.motors.set_head_motor(0),
                       lambda: r.motors.set_lift_motor(0)):
                try:
                    self._call(fn, 3, "stop_motors")
                except Exception:  # noqa: BLE001
                    pass
            self._call(lambda: r.behavior.set_lift_height(0.0), 8, "set_lift_height")
            self._call(lambda: r.behavior.set_head_angle(_deg(15)), 8, "set_head_angle")
            if not jarvis:
                trig = self.c.find_trigger("CelebrateSuccess", "FistBumpSuccess")
                if trig:
                    from anki_vector.messaging import protocol
                    try:
                        self._call(lambda: r.anim.play_animation_trigger(protocol.AnimationTrigger(name=trig),
                                                                         ignore_body_track=True), 15, "play_animation_trigger")
                    except Exception:  # noqa: BLE001
                        pass
        self._say("Routine complete." if jarvis else "Ta-da!")

    def go_to_charger(self):
        self.c.home_tries, self.c.home_asked = 0, False
        self.c._return_home()
