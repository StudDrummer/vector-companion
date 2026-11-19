"""A tour of the full Python SDK (wirepod_vector_sdk) -- more power than the HTTP API:
animations, the face screen, camera frames, cube, events.

Run after setup:  .venv/bin/python examples/sdk_tour.py
"""
import time

import anki_vector
from anki_vector.util import degrees
from PIL import Image, ImageDraw

with anki_vector.Robot(enable_face_detection=True) as robot:
    print("battery:", robot.get_battery_state().battery_level)

    robot.behavior.say_text("Hey Rushil. Long time no see. Let me stretch.")
    robot.anim.play_animation_trigger("GreetAfterLongTime")

    # Drive off the charger, look around
    robot.behavior.drive_off_charger()
    robot.behavior.set_head_angle(degrees(20))
    robot.behavior.turn_in_place(degrees(90))
    robot.behavior.turn_in_place(degrees(-90))

    # Draw on his face screen (184 x 96)
    img = Image.new("RGB", (184, 96), (0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((10, 30), "FOCUS MODE", fill=(50, 215, 75))
    d.text((10, 55), "25:00", fill=(255, 255, 255))
    screen = anki_vector.screen.convert_image_to_screen_data(img)
    robot.screen.set_screen_with_image_data(screen, 4.0)
    time.sleep(4)

    # Grab a camera frame
    robot.camera.init_camera_feed()
    time.sleep(1)
    robot.camera.latest_image.raw_image.save("vector_view.jpg")
    print("saved vector_view.jpg")

    # Who can he see?
    for face in robot.world.visible_faces:
        print("sees face:", face.name or "unknown", face.face_id)

    robot.behavior.drive_on_charger()
