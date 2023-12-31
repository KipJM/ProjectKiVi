"""
Modified from pyopenxr_examples by cmbruns
https://github.com/cmbruns/pyopenxr_examples/
"""

# I really hate python's indentation system
# I want my curly brackets back ;-;
# Don't you just love when the code isn't statically typed and you have no idea what functions does an API expose

import ctypes
import time
from ctypes import cast, byref
from tkinter.filedialog import asksaveasfile

import pygame
import winsound
import xr

VERSION = 1

print("Warning: trackers with role 'Handheld object' won't be detected.")


def accu_sleep(target: int, start_time: int):
    """
    accurate sleep timer. High CPU usage
    :param target: target time in nanoseconds
    :param start_time: perf_counter_ns
    """
    current = time.perf_counter_ns()
    while current - start_time <= target:
        current = time.perf_counter_ns()


# Initialize OpenXR
# ContextObject is a high level pythonic class meant to keep simple cases simple.
with (xr.ContextObject(
        instance_create_info=xr.InstanceCreateInfo(
            enabled_extension_names=[
                # A graphics extension is mandatory (without a headless extension)
                xr.KHR_OPENGL_ENABLE_EXTENSION_NAME,
                xr.extension.HTCX_vive_tracker_interaction.NAME,
            ],
        ),
) as context):
    instance = context.instance
    session = context.session

    # Save the function pointer
    enumerateViveTrackerPathsHTCX = cast(
        xr.get_instance_proc_addr(
            instance,
            "xrEnumerateViveTrackerPathsHTCX",
        ),
        xr.PFN_xrEnumerateViveTrackerPathsHTCX
    )

    # Create the action with subaction path
    # Role strings from
    # https://www.khronos.org/registry/OpenXR/specs/1.0/html/xrspec.html#XR_HTCX_vive_tracker_interaction
    role_strings = [
        "handheld_object",
        "left_foot",
        "right_foot",
        "left_shoulder",
        "right_shoulder",
        "left_elbow",
        "right_elbow",
        "left_knee",
        "right_knee",
        "waist",
        "chest",
        "camera",
        "keyboard",
    ]
    role_path_strings = [f"/user/vive_tracker_htcx/role/{role}"
                         for role in role_strings]
    role_paths = (xr.Path * len(role_path_strings))(
        *[xr.string_to_path(instance, role_string) for role_string in role_path_strings],
    )

    pose_action = xr.create_action(
        action_set=context.default_action_set,
        create_info=xr.ActionCreateInfo(
            action_type=xr.ActionType.POSE_INPUT,
            action_name="tracker_pose",
            localized_action_name="Tracker Pose",
            count_subaction_paths=len(role_paths),
            subaction_paths=role_paths,
        ),
    )

    # Describe a suggested binding for that action and subaction path
    suggested_binding_paths = (xr.ActionSuggestedBinding * len(role_path_strings))(
        *[xr.ActionSuggestedBinding(
            pose_action,
            xr.string_to_path(instance, f"{role_path_string}/input/grip/pose"))
            for role_path_string in role_path_strings],
    )
    xr.suggest_interaction_profile_bindings(
        instance=instance,
        suggested_bindings=xr.InteractionProfileSuggestedBinding(
            interaction_profile=xr.string_to_path(instance, "/interaction_profiles/htc/vive_tracker_htcx"),
            count_suggested_bindings=len(suggested_binding_paths),
            suggested_bindings=suggested_binding_paths,
        )
    )
    # Create action spaces for locating trackers in each role
    tracker_action_spaces = (xr.Space * len(role_paths))(
        *[xr.create_action_space(
            session=session,
            create_info=xr.ActionSpaceCreateInfo(
                action=pose_action,
                subaction_path=role_path,
            )
        ) for role_path in role_paths],
    )

    n_paths = ctypes.c_uint32(0)
    result = enumerateViveTrackerPathsHTCX(instance, 0, byref(n_paths), None)
    if xr.check_result(result).is_exception():
        raise result
    print(xr.Result(result), 0)

    vive_tracker_paths = (xr.ViveTrackerPathsHTCX * n_paths.value)(*([xr.ViveTrackerPathsHTCX()] * n_paths.value))
    result = enumerateViveTrackerPathsHTCX(instance, n_paths, byref(n_paths), vive_tracker_paths)
    if xr.check_result(result).is_exception():
        raise result
    print(xr.Result(result), n_paths.value)
    # print(*vive_tracker_paths)

    # Menu
    print("==Motion Recorder==")
    print("Records the motion of the Vive tracker into a motion data file")

    print("===SETTINGS===")

    print("1. Frame rate")
    print("please enter the framerate of the tracking data.")
    print("It is recommended to record at 2x of the video framerate. For example, if you're shooting at 24fps, "
          "enter 48.")
    sleep_duration = float(1 / float(input("Frame rate(fps): ")))

    print("2. File")
    print("choose where the motion data file will be stored.")
    savefile = asksaveasfile(initialfile='recording', defaultextension=".kvmotion",
                             filetypes=[("KiVi motion data recording", "*.kvmotion")])
    print(f"The file will be saved at {savefile.name}")

    print("==")
    print("Press [SPACE] to clap clapperboard")
    input("press [ENTER] to START RECORDING")

    # File initialization
    savefile.write("KiVi.recording\n")
    savefile.write(f"#version={VERSION}\n")
    savefile.write("#type=raw\n")
    savefile.write('\n')
    savefile.write(f"#step={sleep_duration}\n")
    savefile.write(f"#start_time={time.time()}\n")
    savefile.write("!recording below\n")

    # Setup pygame for sync flash
    pygame.init()
    screen = pygame.display.set_mode((1920, 1080), pygame.RESIZABLE)

    current_frame = 0
    flash_last_frame = False
    screen.fill("black")

    # Loop over the render frames
    for frame_index, frame_state in enumerate(context.frame_loop()):

        # frame timer
        frame_start = time.perf_counter_ns()

        if context.session_state == xr.SessionState.FOCUSED:
            active_action_set = xr.ActiveActionSet(
                action_set=context.default_action_set,
                subaction_path=xr.NULL_PATH,
            )
            xr.sync_actions(
                session=session,
                sync_info=xr.ActionsSyncInfo(
                    count_active_action_sets=1,
                    active_action_sets=ctypes.pointer(active_action_set),
                ),
            )

            n_paths = ctypes.c_uint32(0)
            result = enumerateViveTrackerPathsHTCX(instance, 0, byref(n_paths), None)
            if xr.check_result(result).is_exception():
                raise result

            vive_tracker_paths = (xr.ViveTrackerPathsHTCX * n_paths.value)(
                *([xr.ViveTrackerPathsHTCX()] * n_paths.value))
            # print(xr.Result(result), n_paths.value)
            result = enumerateViveTrackerPathsHTCX(instance, n_paths, byref(n_paths), vive_tracker_paths)
            if xr.check_result(result).is_exception():
                raise result

            # print(xr.Result(result), n_paths.value)
            # print(*vive_tracker_paths)

            found_tracker_count = 0
            for index, space in enumerate(tracker_action_spaces):
                space_location = xr.locate_space(
                    space=space,
                    base_space=context.space,
                    time=frame_state.predicted_display_time,
                )
                if space_location.location_flags & xr.SPACE_LOCATION_POSITION_VALID_BIT:
                    print(f"{role_strings[index]}: {space_location.pose}")
                    found_tracker_count += 1

            if found_tracker_count > 0:
                keys = pygame.key.get_pressed()
                if keys[pygame.K_SPACE] and not flash_last_frame:
                    flash_last_frame = True
                    screen.fill("white")
                    winsound.Beep(2500, 5)
                if not keys[pygame.K_SPACE] and flash_last_frame:
                    screen.fill("black")
                    flash_last_frame = False

            pygame.display.flip()

            if found_tracker_count == 0:
                print("no trackers found")
                savefile.write(f"@{current_frame}~no_tracker\n")

        else:
            # Log standby
            savefile.write(f"@{current_frame}~standby\n")

        # print(current_frame)
        current_frame += 1

        # High precision wait timer. The program doesn't sleep anymore but the precision can reach <1ms, so it's good?
        accu_sleep(int(sleep_duration * 1000000000), time.perf_counter_ns())
