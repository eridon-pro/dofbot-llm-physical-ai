#!/usr/bin/env python3

import json
import os

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from openai import OpenAI


class LLMCommandNode(Node):

    def __init__(self):
        super().__init__("llm_command_node")

        # -------------------------------------------------
        # OpenAI configuration
        # -------------------------------------------------
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. "
                "Run: export OPENAI_API_KEY='your-api-key'"
            )

        self.client = OpenAI(api_key=api_key)

        # Can be overridden:
        # export OPENAI_MODEL=gpt-5-mini
        self.model = os.getenv(
            "OPENAI_MODEL",
            "gpt-5-mini"
        )

        # -------------------------------------------------
        # ROS interfaces
        # -------------------------------------------------

        # Natural-language command comes in here.
        #
        # Example:
        #   "赤いブロックを片付けて"
        self.command_sub = self.create_subscription(
            String,
            "/natural_language_command",
            self.command_callback,
            10
        )

        # Structured robot task goes to llm_color_sorting.py
        #
        # Example:
        #   {"action":"sort","color":"red"}
        self.task_pub = self.create_publisher(
            String,
            "/llm_task",
            10
        )

        self.get_logger().info(
            f"LLM command node started. model={self.model}"
        )

        self.get_logger().info(
            "Waiting for commands on /natural_language_command"
        )

    # =====================================================
    # ROS CALLBACK
    # =====================================================

    def command_callback(self, msg):

        user_command = msg.data.strip()

        if not user_command:
            self.get_logger().warning(
                "Received empty command"
            )
            return

        self.get_logger().info(
            f'Natural language command: "{user_command}"'
        )

        try:
            task = self.parse_command_with_llm(
                user_command
            )

        except Exception as e:
            self.get_logger().error(
                f"OpenAI API error: {e}"
            )
            return

        self.get_logger().info(
            "LLM result: "
            + json.dumps(
                task,
                ensure_ascii=False
            )
        )

        # -------------------------------------------------
        # Safety / capability validation
        # -------------------------------------------------

        if task["action"] == "unsupported":

            self.get_logger().warning(
                "Command is not supported by the robot"
            )
            return

        if task["action"] != "sort":

            self.get_logger().warning(
                f"Unsupported action: {task['action']}"
            )
            return

        valid_colors = {
            "red",
            "green",
            "blue",
            "yellow"
        }

        if task["color"] not in valid_colors:

            self.get_logger().warning(
                f"Unsupported color: {task['color']}"
            )
            return

        # -------------------------------------------------
        # Publish normalized JSON to /llm_task
        # -------------------------------------------------

        robot_task = {
            "action": "sort",
            "color": task["color"]
        }

        output_msg = String()

        output_msg.data = json.dumps(
            robot_task,
            ensure_ascii=False,
            separators=(",", ":")
        )

        self.task_pub.publish(
            output_msg
        )

        self.get_logger().info(
            f"Published /llm_task: {output_msg.data}"
        )

    # =====================================================
    # OPENAI API
    # =====================================================

    def parse_command_with_llm(
        self,
        user_command
    ):

        response = self.client.responses.create(

            model=self.model,

            instructions="""
You are the command interpreter for a Yahboom DOFBOT robotic arm.

Convert the user's natural-language request into a robot task.

The robot currently supports ONLY this capability:

- Find a block of a specified color.
- Pick up that block.
- Move it to the predefined cleanup/sorting location.

Supported colors:
- red
- green
- blue
- yellow

Use:
  action = "sort"
when the user asks to pick, grab, move, sort, put away,
clean up, or otherwise handle one of these colored blocks.

Japanese examples:

「赤いブロックを片付けて」
-> action=sort, color=red

「青色の積み木をつかんで」
-> action=sort, color=blue

「緑のブロックを仕分けて」
-> action=sort, color=green

「黄色いブロックを取って」
-> action=sort, color=yellow

If the request cannot be safely and unambiguously mapped to
one supported color-block sorting action, return:
  action = "unsupported"
  color = "none"

Never invent unsupported robot capabilities.
""",

            input=user_command,

            text={
                "format": {
                    "type": "json_schema",
                    "name": "dofbot_task",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "sort",
                                    "unsupported"
                                ]
                            },
                            "color": {
                                "type": "string",
                                "enum": [
                                    "red",
                                    "green",
                                    "blue",
                                    "yellow",
                                    "none"
                                ]
                            }
                        },
                        "required": [
                            "action",
                            "color"
                        ],
                        "additionalProperties": False
                    }
                }
            }
        )

        task = json.loads(
            response.output_text
        )

        return task


def main(args=None):

    rclpy.init(args=args)

    node = None

    try:

        node = LLMCommandNode()

        rclpy.spin(node)

    except KeyboardInterrupt:

        pass

    except Exception as e:

        print(
            f"llm_command_node failed: {e}"
        )

    finally:

        if node is not None:
            node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
