"""Vector's driving tricks, done with his real motion commands (a regular Vector ignores the 'intents'
WirePod sends for these, which is why Fetch cube etc. used to do nothing).

  fetch_cube     find the cube, pick it up, bring it to you (or set it down where he is)
  roll_cube      find the cube and roll it
  pop_a_wheelie  wheelie off the cube
  come_here      find your face and drive toward you
  explore        drive off the dock and look around, a few short safe hops
  dance          a dance animation (wheels allowed)
  go_to_charger  back to the dock

Each runs in the background and talks: "On it." / what went wrong. All are refused while the dock
lock is on. Cliff and obstacle safety: his own firmware stops actions at cliffs; short hops only.
"""
from __future__ import annotations

import random
import threading
import time

from . import settings as S

ACTIONS = ("fetch_cube", "roll_cube", "pop_a_wheelie", "come_here", "explore", "dance", "go_to_charger")


def _jarvis() -> bool:
    return S.load().get("persona", {}).get("style") == "jarvis"


def _deg(d):
    from anki_vector.util import degrees
    return degrees(d)


def _mm(d):
    from anki_vector.util import distance_mm
    return distance_mm(d)


def _speed(s):
    from anki_vector.util import speed_mmps
    return speed_mmps(s)


class Motion:
    def __init__(self, comp):
        self.c = comp
        self.busy = None
        self.lock = threading.Lock()

    # ------------------------------------------------------------ entry
    def start(self, action: str) -> dict:
        if S.load()["safety"].get("dock_lock"):
            raise PermissionError("The dock lock is on. Turn it off (Drive & Camera or Robot Settings) to let him drive.")
        if not self.lock.acquire(blocking=False):
            raise RuntimeError(f"He's still busy with {self.busy.replace('_', ' ')}.")
        self.busy = action
        threading.Thread(target=self._run, args=(action,), daemon=True).start()
        return {"started": action}

    def _run(self, action: str):
        from .companion import log
        log(f"motion: {action}")
        try:
            getattr(self, action)()
        except Exception as e:  # noqa: BLE001
            msg = str(e) or e.__class__.__name__
            log(f"motion: {action} failed: {msg}")
            self._say(self._friendly(action, msg))
        finally:
            self.c.cube_handled_until = time.time() + 5  # the cube settling after he lets go isn't a tap
            self.busy = None
            self.lock.release()

    @staticmethod
    def _friendly(action, msg):
        m = msg.lower()
        if "cube" in m and ("not" in m or "find" in m or "no " in m):
            return "I can't find my cube. Put it in front of me and try again."
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
        seen = lambda: bool(cube and cube.is_visible)  # noqa: E731
        log(f"motion: cube connected={bool(r.world.connected_light_cube)} visible={seen()} "
            f"on_charger={r.status.is_on_charger}")
        if seen() or not search:
            return cube
        self._call(lambda: r.behavior.set_lift_height(0.0), 10, "set_lift_height")
        for head in (-5, 10):  # look low first, then a little higher
            self._call(lambda: r.behavior.set_head_angle(_deg(head)), 10, "set_head_angle")
            for step in range(8):  # a full circle in 45-degree steps
                time.sleep(1.2)  # give his vision a moment to recognise the markers
                if seen():
                    log(f"motion: cube spotted (head {head}, step {step})")
                    return cube
                self._call(lambda: r.behavior.turn_in_place(_deg(45)), 15, "turn_in_place")
            if head == -5:  # maybe he's too close to it: back up a little and look again
                self._call(lambda: r.behavior.drive_straight(_mm(-80), _speed(60)), 15, "drive_straight")
        raise RuntimeError("couldn't find the cube")

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
        with self.c.control():
            r = self.c.raw  # unwrapped: these calls get their own long time limits below
            self._say("Fetching my cube.")
            self._off_dock(r)
            cube = self._cube(r)
            self.c.cube_color("blue")
            self._call(lambda: r.behavior.pickup_object(cube, num_retries=2), 60, "pickup_object")
            if self._face_turn(r):
                self._call(lambda: r.behavior.drive_straight(_mm(150), _speed(60)), 20, "drive_straight")
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
            self._call(lambda: r.behavior.drive_straight(_mm(200), _speed(80)), 25, "drive_straight")
            self._call(lambda: r.behavior.set_head_angle(_deg(35)), 10, "set_head_angle")
        self._say("Here I am, sir." if _jarvis() else "Hi!")

    def explore(self):
        with self.c.control():
            r = self.c.raw  # unwrapped: these calls get their own long time limits below
            self._say("Off I go.")
            self._off_dock(r)
            self._call(lambda: r.behavior.set_head_angle(_deg(0)), 10, "set_head_angle")
            for _ in range(5):
                self._call(lambda: r.behavior.turn_in_place(_deg(random.choice([-90, -45, 45, 90, 135]))),
                           15, "turn_in_place")
                p = r.proximity.last_sensor_reading
                clear = not (p and p.found_object and p.distance.distance_mm < 150)
                if clear and not r.status.is_cliff_detected:
                    self._call(lambda: r.behavior.drive_straight(_mm(120), _speed(70)), 20, "drive_straight")
                time.sleep(0.5)
            try:
                self._call(lambda: r.behavior.look_around_in_place(), 60, "look_around_in_place")
            except Exception:  # noqa: BLE001
                pass
        self._say("Nice desk, sir." if _jarvis() else "That was fun!")

    def dance(self):
        from anki_vector.messaging import protocol
        trig = self.c.find_trigger("DanceBeatGetIn", "Dance", "Celebrate") or "CelebrateSuccess"
        with self.c.control():
            r = self.c.raw  # unwrapped: these calls get their own long time limits below
            self._off_dock(r)
            for t in [trig] + [x for x in self.c.triggers if "Dance" in x and x != trig][:2]:
                self._call(lambda: r.anim.play_animation_trigger(protocol.AnimationTrigger(name=t)), 30,
                           "play_animation_trigger")

    def go_to_charger(self):
        with self.c.control():
            r = self.c.raw  # unwrapped: these calls get their own long time limits below
            self._call(lambda: r.behavior.drive_on_charger(), 60, "drive_on_charger")
