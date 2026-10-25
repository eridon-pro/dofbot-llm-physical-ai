# DOFBOT-Pi × LLM による自然言語ロボット操作

## 1. 課題概要

本課題では、Yahboom DOFBOT-Pi ロボットアームを使用し、LLMによる自然言語理解、ROS 2、Computer Visionを組み合わせて、自然言語による指示から実機ロボットの動作までを実行するPhysical AIシステムを構築した。

### 使用したロボット：[DOFBOT-Pi](https://www.yahboom.store/collections/dofbot/products/dofbot-pi)

DOFBOT-Piは、Yahboom社が提供するRaspberry Piベースの6DoFロボットアームで、6個のバスサーボとカメラを搭載している。

ROS 2 Humble、Python、OpenCVを利用した開発環境が用意されており、基本的なサーボ制御に加えて、色認識、物体位置検出、Visual Tracking、Visual Grasping、Inverse Kinematicsなどを利用したロボットアーム制御を行うことができる。

本課題では、DOFBOT-Pi公式環境が提供するカメラ、色認識、Inverse Kinematics、把持処理などの既存機能を活用し、その上にLLMによる自然言語インターフェースを追加した。

### ベースラインとした実装

本課題を検討するにあたり、以下のQiita記事をベースラインの一つとした。

**ChatGPT APIを使って自然言語の指示でGazebo上のTurtleBot3を制御する**

https://qiita.com/porizou1/items/a085d20e936946330540

この実装では、例えば、

> 「0.2m/sで前に進む」

という自然言語による指示をChatGPTへ入力し、ChatGPTにROS 2のPythonノードを生成させる。

生成されたPythonコードをファイルとして保存し、`subprocess`から実行することで、Gazebo上のTurtleBot3を制御している。

処理の概略は以下のようになる。

```text
自然言語による指示
        ↓
ChatGPT API
        ↓
ROS 2 Pythonコードを生成
        ↓
生成したコードを実行
        ↓
Gazebo上のTurtleBot3を制御
```

### ベースラインとの違い

本課題では、この「自然言語からROS 2ロボットを操作する」という考え方を参考にしつつ、主に以下の3点を変更した。

#### 1. シミュレータではなく実機を使用

ベンチマークではGazebo上のTurtleBot3を制御するのに対し、本課題ではDOFBOT-Pi実機を使用する。

そのため、単純な速度指令だけでなく、

- カメラ画像の取得
- 対象物の色認識
- 対象位置の推定
- Inverse Kinematics
- サーボ制御
- グリッパによる把持

といった、実世界との相互作用を含む処理が必要となる。

#### 2. LLMにROS 2コードそのものを生成させない

ベースラインでは、LLMがROS 2 Pythonコードを生成し、そのコードを直接実行する。

一方、本課題ではLLMの役割を自然言語の意味解釈と高レベルなタスク生成に限定した。

例えば、

> 「赤いブロックを片付けて」

という指示に対して、LLMは以下のような構造化されたJSONのみを生成する。

```json
{
  "action": "sort",
  "color": "red"
}
```

このJSONをROS 2側で検証し、あらかじめ用意したROS 2ノードのみが実機を制御する。

これにより、LLMが生成した任意のPythonコードをそのまま実機で実行する方式と比較して、実行可能な操作を限定し、安全性と再現性を高めることを狙った。

#### 3. 自然言語からPhysical Actionまでを接続

本課題では、LLMによる自然言語理解だけでなく、その後のComputer Vision、位置推定、Inverse Kinematics、実機ロボット制御までを一つのパイプラインとして接続した。

```text
Natural Language
        ↓
OpenAI LLM
        ↓
Structured JSON
        ↓
ROS 2
        ↓
Computer Vision
        ↓
Target Position Estimation
        ↓
Inverse Kinematics
        ↓
DOFBOT-Pi Physical Action
```

つまり、ベースラインの

**「自然言語 → ROS 2コード生成 → シミュレーションロボット制御」**

という構成を、本課題では

**「自然言語 → 構造化タスク生成 → Vision → 実機ロボット制御」**

へ発展させた。

---

## 2. 目的

本課題では、LLMとPhysical AIを組み合わせ、自然言語による高レベルな指示から実世界のロボット動作までを接続することを目的とした。

特に、より安全で再利用性の高い構成を目指し、LLMには低レベルなロボット制御コードを生成させず、「何を行うか」という高レベルなタスクのみをJSONとして生成させる方式とした。

これにより、

- **LLM**：自然言語の解釈とタスク生成
- **ROS 2**：タスクの受け渡しと決定論的なロボット制御
- **Computer Vision**：対象物の認識と位置推定
- **DOFBOT-Pi**：実世界での把持・移動

という役割分担を行った。

---

## 3. システム構成

処理の流れは以下の通り。

```text
自然言語
「赤いブロックを片付けて」
        │
        ▼
llm_command_node
        │
        │ OpenAI API
        ▼
{"action":"sort","color":"red"}
        │
        ▼
/llm_task
        │
        ▼
llm_color_sorting
        │
        │ /image_raw
        ▼
色認識・対象位置推定
        │
        ▼
/PosInfo
        │
        ▼
DOFBOT標準 grasp node
        │
        ▼
IK・サーボ制御
        │
        ▼
DOFBOT-Pi 実機
```

---

## 4. 使用環境

- Yahboom DOFBOT-Pi
- Raspberry Pi 5
- ROS 2 Humble
- Yahboom DOFBOT公式Docker環境
- Python 3.10
- OpenCV
- OpenAI API
- ROS 2 `rclpy`

DOFBOT公式環境に含まれる以下の機能を利用した。

- `dofbot_info`
- `dofbot_sorting`
- `grasp`
- `camera_arm_kin.launch.py`
- `dofbot_interface/msg/AprilTagInfo`

---

## 5. Dockerコンテナ内のファイル構成

本課題では、Yahboom DOFBOT公式Docker環境内の
`/root/dofbot_ws/src/dofbot_sorting/` を利用した。

今回、新規作成・変更した主なファイルは以下の通り。

```text
/root/dofbot_ws/
└── src/
    └── dofbot_sorting/
        ├── setup.py                     # 編集。llm_command_node、llm_color_sorting を
        │                                  ROS 2 executableとして登録
        └── dofbot_sorting/
            ├── color_sorting.py         # Yahboom標準
            ├── llm_color_sorting.py     # 新規作成。/llm_task をsubscribe。指定色を画像認識し、
            │                              対象位置を計算して /PosInfo にpublish
            ├── llm_command_node.py      # 新規作成。自然言語をOpenAI APIへ送信。LLM出力を
            │                              構造化JSONへ変換し、/llm_task にpublish
            ├── color_common.py          # Yahboom標準
            ├── compute_joint5.py        # Yahboom標準
            ├── red_colorHSV.text        # Yahboom標準
            ├── green_colorHSV.text      # Yahboom標準
            ├── blue_colorHSV.text       # Yahboom標準
            └── yellow_colorHSV.text     # Yahboom標準
```

---

## 6. 作成したROS 2ノード

### llm_command_node

自然言語による指示を `/natural_language_command` から受信し、OpenAI APIへ送信する。

LLMから得られた結果を以下の形式へ正規化する。

```json
{
  "action": "sort",
  "color": "blue"
}
```

生成したJSONを `/llm_task` トピックへpublishする。

現在対応している色は以下の4色。

- red
- green
- blue
- yellow

サポートしていない指示については、ロボットを動作させないようにしている。

### llm_color_sorting

`/llm_task` のJSONを受信し、指定された色を認識する。

カメラ画像 `/image_raw` に対してHSVベースの色認識を行い、対象ブロックの画像上の位置からロボット座標を計算する。

認識結果を `dofbot_interface/msg/AprilTagInfo` 型の `/PosInfo` としてpublishする。

例：

```text
id: 3
x: 0.23348
y: 0.04552
z: 0.030
```

この情報をDOFBOT標準の `grasp` ノードが受け取り、Inverse Kinematicsによってアームを制御する。

---

## 7. 実行方法

最初にDOFBOT標準APPを停止する。

```bash
cd /root/APP_DOFBOT
sh kill_app.sh
```

### Terminal 1：カメラ・IK

```bash
ros2 launch dofbot_info camera_arm_kin.launch.py
```

### Terminal 2：把持ノード

```bash
ros2 run dofbot_sorting grasp
```

### Terminal 3：LLM対応色認識ノード

```bash
ros2 run dofbot_sorting llm_color_sorting
```

### Terminal 4：LLMコマンドノード

OpenAI APIキーを環境変数へ設定する。

```bash
export OPENAI_API_KEY="YOUR_API_KEY"
```

その後、

```bash
ros2 run dofbot_sorting llm_command_node
```

を実行する。

### Terminal 5：自然言語による指示

例えば、

```bash
ros2 topic pub --once \
/natural_language_command \
std_msgs/msg/String \
"{data: '赤いブロックを片付けて'}"
```

と入力する。

LLMによって、

```json
{
  "action": "sort",
  "color": "red"
}
```

へ変換され、対象ブロックの認識・把持・移動が開始される。

---

## 8. 工夫した点

### LLMに直接ロボット制御コードを書かせない

LLMが生成した任意のPythonコードをそのまま実機で実行する方式では、安全性や再現性の問題がある。

そこで本システムでは、LLMの出力を限定されたJSON形式とし、実際のロボット制御は事前に用意したROS 2ノードのみが実行する構成とした。

これにより、LLMと物理ロボットの間に明確な制御境界を設けた。

### 既存のROS 2機能を再利用

カメラ、Inverse Kinematics、Servo制御、把持処理をすべて作り直すのではなく、DOFBOT公式ROS 2環境の既存ノードを再利用した。

その上で、自然言語からロボットタスクへ変換する部分を追加した。

### Structured Command

LLM出力を自由文ではなく、

```json
{
  "action": "sort",
  "color": "red"
}
```

のような構造化されたコマンドとすることで、ROS 2側で入力値を検証できるようにした。

---

## 9. 実験結果

自然言語による以下のような指示から、対象色の選択、画像認識、位置推定、アーム制御まで一連の処理が実行できることを確認した。

```text
「赤いブロックを片付けて」
「青いブロックを片付けて」
```

例えば青ブロックについては、LLMによって以下のJSONが生成された。

```json
{
  "action": "sort",
  "color": "blue"
}
```

ROS 2側では対象物を認識し、

```text
Publishing PosInfo:
id=3
x=0.23348
y=0.04552
z=0.030
```

のような把持位置情報を生成し、実機アームを動作させることができた。

デモ動画では、把持に失敗するケースと、対象物の把持・移動に成功するケースの両方を示している。

---

## 10. 課題・制約

現状では、画像上の対象位置からロボット座標への変換精度に課題がある。

対象ブロックの位置によっては、推定された把持位置と実際の位置にずれが生じ、アームがブロック付近まで移動しても正確に把持できない場合がある。

原因として、

- カメラとロボット座標系のキャリブレーション誤差
- 画像座標から実空間座標への簡易変換
- サーボのバックラッシュ
- ブロックの姿勢
- 色認識領域の重心誤差

などが考えられる。

一方で、自然言語からPhysical Actionまでのパイプラインについては一連の動作を確認できた。

---

## 11. 今後の改善

今後は以下を改善したい。

- カメラキャリブレーションおよび座標変換精度の向上
- 複数物体から対象物を選択する認識処理
- RGB-Dカメラなどを利用した3次元位置推定
- LLMが複数ステップのタスクプランを生成する機能
- ROS 2 Actionを利用したタスク実行状態の管理
- 異常時の停止・リトライ処理
- 対応する物体やタスクの拡張

---

## 12. まとめ

本課題では、DOFBOT-Pi、ROS 2、Computer Vision、LLMを組み合わせ、自然言語から実世界のロボット動作までを接続するPhysical AIシステムを構築した。

ベンチマークとした「自然言語からLLMがROS 2コードを生成し、ロボットを制御する」というアプローチを参考にしつつ、本課題ではLLMに直接サーボやROS 2コードを生成させるのではなく、高レベルなタスクを構造化JSONとして生成し、検証済みのROS 2ノードが実機制御を担当する構成とした。

実機では把持位置精度に課題が残ったものの、

**Natural Language → LLM → Structured Command → Vision → Position Estimation → Robot Control → Physical Action**

という一連のパイプラインを実機上で確認することができた。
