# TaskFlow PySide6 - Auto Layout Sample

## Install

```bash
pip install .
```

For editable development installs:

```bash
pip install -e .
```

## Run

```bash
pytaskflow
```

You can also run it as a module:

```bash
python -m pytaskflow
```

PySide6 + QGraphicsView + JSON の工程依存関係ビューアです。

## 追加した自動配置

### 完全自動配置
- 依存関係の深さから列番号を決定
- 同列内の工程を自動で行配置
- 前提工程群の中央へ後続工程を寄せる
- barycenter法の簡易版で、線の交差を減らすよう行順を調整
- 循環依存を検出

### 列だけ整列
- 依存関係からX座標だけを再計算
- Y座標はユーザーの手動配置を維持

## インストール

```bash
pip install PySide6
```

## 起動

```bash
python main.py
```

## 操作

- `完全自動配置` : 列・行を自動配置
- `列だけ整列` : X座標だけ自動配置
- ノードをドラッグ : 手動微調整
- `Ctrl + マウスホイール` : ズーム
- ノードをダブルクリック : 登録フォルダをExplorerで開く
- ノードを右クリック : 状態変更 / フォルダを開く
- `保存` : 配置をJSONへ保存

## 列番号のルール

```text
column(task) = 0                              前提工程なし
column(task) = max(column(predecessor)) + 1   前提工程あり
```
