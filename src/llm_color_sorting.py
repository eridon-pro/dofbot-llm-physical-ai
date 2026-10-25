#!/usr/bin/env python3

import os
import json
import time
import threading

import cv2
import cv2 as cv
import numpy as np
import yaml

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import Image
from std_msgs.msg import Bool, Int16, String
from cv_bridge import CvBridge

from Arm_Lib import Arm_Device

from dofbot_sorting.color_common import *
from dofbot_sorting.compute_joint5 import *
from dofbot_interface.msg import AprilTagInfo
from dofbot_interface.srv import Kinemarics

from ament_index_python import get_package_share_directory


print(cv2.__version__)

package_pwd = "/root/dofbot_ws/src/dofbot_sorting/dofbot_sorting/"

# Camera brightness
os.system(
    "sudo v4l2-ctl -d /dev/video0 -c brightness=10"
)

# ---------------------------------------------------------
# Load camera/arm calibration offsets
# ---------------------------------------------------------
pkg_path = get_package_share_directory("dofbot_sorting")
offset_file = os.path.join(pkg_path, "config", "offset.yaml")

with open(offset_file, "r") as file:
    offset_config = yaml.safe_load(file)

print("offset config:", offset_config)


class ColorRecognizeNode(Node):

    def __init__(self, name):
        super().__init__(name)

        self.Arm = Arm_Device()

        # -------------------------------------------------
        # Calibration parameters
        # -------------------------------------------------
        self.init_joints = offset_config.get(
            "init_joints",
            [90.0, 110.0, 0.0, 0.0, 90.0, 0.0]
        )

        self.x_offset = offset_config.get("x_offset", 0.0)
        self.y_offset = offset_config.get("y_offset", 0.0)

        self.get_logger().info(
            f"offset: x={self.x_offset}, y={self.y_offset}"
        )

        # -------------------------------------------------
        # ROS interfaces
        # -------------------------------------------------
        self.rgb_bridge = CvBridge()

        self.sub_grasp_status = self.create_subscription(
            Bool,
            "grasp_done",
            self.get_graspStatusCallBack,
            100
        )

        self.pos_info_pub = self.create_publisher(
            AprilTagInfo,
            "PosInfo",
            1
        )

        self.pub_joint5 = self.create_publisher(
            Int16,
            "set_joint5",
            10
        )

        # JSON task interface
        self.llm_task_sub = self.create_subscription(
            String,
            "/llm_task",
            self.llm_task_callback,
            10
        )

        # Camera
        self.subscription = self.create_subscription(
            Image,
            "/image_raw",
            self.ImageCallback,
            1
        )

        # -------------------------------------------------
        # Color configuration
        # -------------------------------------------------
        self.target_color = 0
        self.cur_target_color = 0

        self.red_hsv_text = os.path.join(
            package_pwd,
            "red_colorHSV.text"
        )

        self.green_hsv_text = os.path.join(
            package_pwd,
            "green_colorHSV.text"
        )

        self.blue_hsv_text = os.path.join(
            package_pwd,
            "blue_colorHSV.text"
        )

        self.yellow_hsv_text = os.path.join(
            package_pwd,
            "yellow_colorHSV.text"
        )

        self.hsv_range = ()

        # -------------------------------------------------
        # Vision state
        # -------------------------------------------------
        self.select_flags = False
        self.windows_name = "frame"
        self.Track_state = "init"

        self.Mouse_XY = (0, 0)

        self.cols = 0
        self.rows = 0

        self.Roi_init = ()

        self.color = color_detect()

        self.cur_color = None
        self.text_color = (0, 0, 0)

        self.cx = 0
        self.cy = 0

        self.circle_r = 0

        self.joint5 = Int16()

        self.corners = np.empty(
            (4, 2),
            dtype=np.int32
        )

        self.updata_flag = False

        # Equivalent to pressing Space when True
        self.pub_pos_flag = False

        # Move arm to initial camera-viewing pose
        self.Arm.Arm_serial_servo_write6_array(
            self.init_joints,
            2000
        )

        self.get_logger().info("ColorRecognizeNode initialized")

    # =====================================================
    # LLM / JSON COMMAND CALLBACK
    # =====================================================

    def llm_task_callback(self, msg):

        self.get_logger().info(
            f"Received task: {msg.data}"
        )

        try:
            command = json.loads(msg.data)

        except json.JSONDecodeError as e:
            self.get_logger().error(
                f"Invalid JSON: {e}"
            )
            return

        action = command.get("action")
        color = command.get("color")

        # -------------------------------------------------
        # Validate command
        # -------------------------------------------------
        if action != "sort":
            self.get_logger().error(
                f"Unsupported action: {action}"
            )
            return

        color_map = {
            "red": 1,
            "green": 2,
            "blue": 3,
            "yellow": 4,
        }

        if color not in color_map:
            self.get_logger().error(
                f"Unsupported color: {color}"
            )
            return

        # -------------------------------------------------
        # Set target
        # -------------------------------------------------
        self.target_color = color_map[color]
        self.cur_target_color = self.target_color

        self.Track_state = "identify"

        # Equivalent to Space key:
        # publish target position as soon as the target is detected
        self.pub_pos_flag = True

        self.get_logger().info(
            f"Task accepted: action={action}, color={color}"
        )

    # =====================================================
    # GRASP STATUS CALLBACK
    # =====================================================

    def get_graspStatusCallBack(self, msg):

        if msg.data is True:

            self.get_logger().info(
                "Grasp completed"
            )

            time.sleep(2)

            # Original program allows another position publication
            # after grasp completion.
            self.pub_pos_flag = True

    # =====================================================
    # RESET
    # =====================================================

    def Reset(self):

        self.hsv_range = ()

        self.circle = (0, 0, 0)

        self.Mouse_XY = (0, 0)

        self.Track_state = "init"

        print("Change the state.")

        self.cx = 0
        self.cy = 0

        self.pub_pos_flag = False

    # =====================================================
    # DISPLAY
    # =====================================================

    def img_out(self, result_frame, binary):

        if len(binary) != 0:

            cv.imshow(
                self.windows_name,
                ManyImgs(
                    0.8,
                    ([result_frame, binary])
                )
            )

        else:

            cv.imshow(
                self.windows_name,
                result_frame
            )

    # =====================================================
    # MOUSE CALLBACK FOR HSV CALIBRATION
    # =====================================================

    def onMouse(self, event, x, y, flags, param):

        if event == 1:

            self.Track_state = "init"

            self.select_flags = True

            self.Mouse_XY = (x, y)

        if event == 4:

            self.select_flags = False

            self.Track_state = "select"

        if self.select_flags is True:

            self.cols = (
                min(self.Mouse_XY[0], x),
                min(self.Mouse_XY[1], y),
            )

            self.rows = (
                max(self.Mouse_XY[0], x),
                max(self.Mouse_XY[1], y),
            )

            self.Roi_init = (
                self.cols[0],
                self.cols[1],
                self.rows[0],
                self.rows[1],
            )

    # =====================================================
    # CAMERA CALLBACK
    # =====================================================

    def ImageCallback(self, color_frame):

        # Convert ROS Image -> OpenCV
        rgb_image = self.rgb_bridge.imgmsg_to_cv2(
            color_frame,
            "rgb8"
        )

        rgb_image = cv2.cvtColor(
            rgb_image,
            cv2.COLOR_RGB2BGR
        )

        # Keep keyboard operation for debugging
        key = cv2.waitKey(10) & 0xFF

        result_frame, binary = self.process(
            rgb_image,
            key
        )

        show_frame = threading.Thread(
            target=self.img_out,
            args=(
                result_frame,
                binary,
            )
        )

        show_frame.start()
        show_frame.join()

        # -------------------------------------------------
        # Space key still works manually
        # -------------------------------------------------
        if key == 32:
            self.pub_pos_flag = True

        # -------------------------------------------------
        # Target detected
        # -------------------------------------------------
        if (
            self.cx != 0
            and self.cy != 0
            and self.circle_r > 30
        ):

            cx = int(self.cx)
            cy = int(self.cy)

            # -------------------------------------------------
            # Pixel -> robot coordinates
            #
            # Preserve calibration offset from original
            # dofbot_sorting implementation.
            # -------------------------------------------------
            a = round(
                ((320 - cx) / 4000)
                + self.y_offset,
                5
            )

            b = round(
                ((480 - cy) / 3000)
                * 0.8
                + 0.15
                + self.x_offset,
                5
            )

            # Calculate wrist rotation
            vx = (
                self.corners[0][0][0]
                - self.corners[1][0][0]
            )

            vy = (
                self.corners[0][0][1]
                - self.corners[1][0][1]
            )

            target_joint5 = compute_joint5(
                vx,
                vy
            )

            print(
                "target_joint5:",
                target_joint5
            )

            # -------------------------------------------------
            # Publish once when requested
            # -------------------------------------------------
            if self.pub_pos_flag is True:

                self.pub_pos_flag = False

                joint5 = Int16()

                joint5.data = int(
                    target_joint5
                )

                self.pub_joint5.publish(
                    joint5
                )

                pos = AprilTagInfo()

                pos.id = int(
                    self.cur_target_color
                )

                pos.x = float(b)
                pos.y = float(a)
                pos.z = 0.03

                self.get_logger().info(
                    "Publishing PosInfo: "
                    f"id={pos.id}, "
                    f"x={pos.x:.5f}, "
                    f"y={pos.y:.5f}, "
                    f"z={pos.z:.3f}"
                )

                self.pos_info_pub.publish(
                    pos
                )

    # =====================================================
    # COLOR PROCESSING
    # =====================================================

    def process(self, rgb_img, key):

        rgb_img = cv.resize(
            rgb_img,
            (640, 480)
        )

        binary = []

        # -------------------------------------------------
        # Keep original keyboard control
        # -------------------------------------------------

        if key == ord("c") or key == ord("C"):

            self.target_color = 0

            self.Reset()

            self.updata_flag = True

        elif key == ord("r") or key == ord("R"):

            self.target_color = 1
            self.cur_target_color = 1

        elif key == ord("g") or key == ord("G"):

            self.target_color = 2
            self.cur_target_color = 2

        elif key == ord("b") or key == ord("B"):

            self.target_color = 3
            self.cur_target_color = 3

        elif key == ord("y") or key == ord("Y"):

            self.target_color = 4
            self.cur_target_color = 4

        elif (
            key == ord("i")
            or key == ord("I")
            or self.target_color != 0
        ):

            self.Track_state = "identify"

        # -------------------------------------------------
        # HSV calibration mode
        # -------------------------------------------------

        if self.Track_state == "init":

            cv.namedWindow(
                self.windows_name,
                cv.WINDOW_AUTOSIZE
            )

            cv.setMouseCallback(
                self.windows_name,
                self.onMouse,
                0
            )

            if self.select_flags is True:

                cv.line(
                    rgb_img,
                    self.cols,
                    self.rows,
                    (255, 0, 0),
                    2
                )

                cv.rectangle(
                    rgb_img,
                    self.cols,
                    self.rows,
                    (0, 255, 0),
                    2
                )

                if (
                    self.Roi_init[0]
                    != self.Roi_init[2]
                    and self.Roi_init[1]
                    != self.Roi_init[3]
                ):

                    rgb_img, self.hsv_range = (
                        self.color.Roi_hsv(
                            rgb_img,
                            self.Roi_init
                        )
                    )

                    self.dyn_update = True

                else:

                    self.Track_state = "init"

        # -------------------------------------------------
        # Identify requested color
        # -------------------------------------------------

        elif self.Track_state == "identify":

            if self.target_color == 1:

                self.hsv_range = read_HSV(
                    self.red_hsv_text
                )

                self.cur_color = "red"

                self.text_color = (
                    0,
                    0,
                    255
                )

            elif self.target_color == 2:

                self.hsv_range = read_HSV(
                    self.green_hsv_text
                )

                self.cur_color = "green"

                self.text_color = (
                    0,
                    255,
                    0
                )

            elif self.target_color == 3:

                self.hsv_range = read_HSV(
                    self.blue_hsv_text
                )

                self.cur_color = "blue"

                self.text_color = (
                    255,
                    0,
                    0
                )

            elif self.target_color == 4:

                self.hsv_range = read_HSV(
                    self.yellow_hsv_text
                )

                self.cur_color = "yellow"

                self.text_color = (
                    255,
                    255,
                    0
                )

            else:

                self.Track_state = "init"

        # -------------------------------------------------
        # Object detection
        # -------------------------------------------------

        if self.Track_state != "init":

            if len(self.hsv_range) != 0:

                (
                    rgb_img,
                    binary,
                    self.circle,
                    _,
                    self.corners
                ) = self.color.object_follow(
                    rgb_img,
                    self.hsv_range
                )

                self.cx = self.circle[0]
                self.cy = self.circle[1]
                self.circle_r = self.circle[2]

                # Save recalibrated HSV range
                if (
                    self.cur_target_color == 1
                    and self.updata_flag is True
                ):

                    write_HSV(
                        self.red_hsv_text,
                        self.hsv_range
                    )

                elif (
                    self.cur_target_color == 2
                    and self.updata_flag is True
                ):

                    write_HSV(
                        self.green_hsv_text,
                        self.hsv_range
                    )

                elif (
                    self.cur_target_color == 3
                    and self.updata_flag is True
                ):

                    write_HSV(
                        self.blue_hsv_text,
                        self.hsv_range
                    )

                elif (
                    self.cur_target_color == 4
                    and self.updata_flag is True
                ):

                    write_HSV(
                        self.yellow_hsv_text,
                        self.hsv_range
                    )

                self.updata_flag = False

        # -------------------------------------------------
        # Display selected color
        # -------------------------------------------------

        if self.cur_color is not None:

            rgb_img = cv2.putText(
                rgb_img,
                self.cur_color,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                self.text_color,
                2
            )

        return rgb_img, binary


def main(args=None):

    print("----------------------")
    print("DOFBOT LLM Color Sorting")
    print("----------------------")

    rclpy.init(args=args)

    color_recognize = ColorRecognizeNode(
        "llm_ColorRecognize_node"
    )

    try:

        rclpy.spin(
            color_recognize
        )

    except KeyboardInterrupt:

        pass

    finally:

        color_recognize.destroy_node()

        rclpy.shutdown()

        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
