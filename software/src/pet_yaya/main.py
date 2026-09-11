from __future__ import annotations

import signal
from contextlib import contextmanager

from pet_yaya.application.session_manager import InteractionBlockedError
from pet_yaya.bootstrap import build_simulator
from pet_yaya.adapters.simulator import ConsoleActuator
from pet_yaya.domain.cancellation import CancellationToken, DialogueCancelled
from pet_yaya.domain.models import ConfirmedMemory
from pet_yaya.domain.voice_confirmation import parse_memory_confirmation


HELP = """
命令：
  /yes       批准最近一条待确认记忆
  /no        拒绝最近一条待确认记忆
  /memory    查看已确认记忆（/memories 也可以）
  /forget N  按列表编号删除一条长期记忆
  /growth    查看成长状态
  /clearhistory 清空短期对话历史，保留长期记忆和成长值
  /model     查看当前对话引擎、模型和降级状态
  /listen    开始录音，说完停顿自动结束，Enter 可提前结束
  /endpoint off 切回手动结束录音（Enter结束或到达时限）
  /endpoint on  恢复人声检测自动结束（默认）
  /pause N   普通聊天停顿等待秒数，1到5，默认2.5；例如 /pause 3
  /review on 开启识别文字的手动确认（调试用）
  /review off 关闭手动确认（默认）
  /voice on  开启回答朗读（语音版默认开启）
  /voice off 关闭回答朗读，不影响文字聊天
  /status    查看会话与虚拟设备状态
  /mute      模拟麦克风静音
  /unmute    解除麦克风静音
  /offline   模拟网络断开（继续使用本地规则）
  /online    模拟网络恢复
  /battery N 设置虚拟电量，例如 /battery 10
  /touch     模拟摸头
  /collision 模拟碰撞并停止当前行为
  /interrupt 重置会话状态；生成过程中按 Ctrl+C 停止回复
  /events    查看最近 10 个事件
  /reset yes 清除全部记忆和成长状态
  /help      查看命令
  /quit      退出
""".strip()


def resolve_memory_id(
    reference: str, memories: tuple[ConfirmedMemory, ...]
) -> str | None:
    """Resolve a user-facing list number or an exact memory ID."""
    cleaned = reference.strip()
    if not cleaned:
        return None
    if cleaned.isdigit():
        position = int(cleaned)
        if 1 <= position <= len(memories):
            return memories[position - 1].id
        return None
    return cleaned


@contextmanager
def cancel_on_ctrl_c(token: CancellationToken):
    previous = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, lambda signum, frame: token.cancel())
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)


def confirm_by_voice(yaya, voice, pending_id):
    """At most two recordings; revised content always needs a new approval."""
    approved = False
    reason = "未收到明确同意，本条记忆不保存。"
    try:
        if yaya.session_status().muted:
            raise RuntimeError("麦克风已静音")
        for attempt in range(2):
            print("即将听取记忆确认：提示音后自然回答，例如‘可以啊’或‘不要’，最长录音5秒。", flush=True)
            token = CancellationToken()
            with cancel_on_ctrl_c(token):
                recognized = voice.listen(token, confirmation=True)
                token.check()
                decision = yaya.interpret_confirmation(pending_id, recognized, token)
            print(f"确认识别：{recognized}")
            if decision.intent in {"approve", "reject"}:
                approved = decision.intent == "approve"
                if not approved:
                    reason = "好的，我不会保存。"
                break
            if attempt == 0:
                question = (f"改为记住：『{decision.content}』。可以保存吗？" if decision.intent == "revise"
                            else "我还没确定你的意思。你同意保存刚才那条记忆吗？可以说可以啊，或者不要。")
                print("Yaya：" + question)
                token = CancellationToken()
                with cancel_on_ctrl_c(token):
                    voice.speak(question + " 请在提示音后回答。", token)
                    token.check()
    except (DialogueCancelled, KeyboardInterrupt):
        reason = "确认已取消，本条记忆不保存。"
    except Exception as error:
        print(f"语音确认失败：{error}")
    handled = yaya.confirm_memory(pending_id, approved)
    message = ("我记住了！" if approved else reason) if handled else "这条待确认记忆已不存在。"
    print(f"Yaya：{message}")
    try:
        token = CancellationToken()
        with cancel_on_ctrl_c(token):
            voice.speak(message, token)
    except (DialogueCancelled, KeyboardInterrupt):
        print("提示朗读已停止，记忆处理结果不变。")
    except Exception as error:
        print(f"提示朗读失败：{error}；记忆处理结果不变。")


def main(voice=None) -> None:
    try:
        _main(voice)
    finally:
        if voice is not None:
            voice.close()


def _main(voice=None) -> None:
    console = ConsoleActuator()
    yaya = build_simulator(actuator=console)
    latest_pending_id: str | None = None
    review_transcript = False
    print("Pet Yaya 软件模拟器已启动。输入 /help 查看命令。")
    print("本地普通回复逐步显示；生成过程中按 Ctrl+C 停止，等待输入时按 Ctrl+C 退出。")
    if voice is not None:
        print("语音版：/listen 开始录音，识别后直接回答；记忆询问朗读完会自动听取一次确认。")
        print("/review on 开启手动检查文字；/voice off 关闭朗读和自动记忆确认录音。")

    while True:
        from_voice = False
        try:
            text = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            yaya.shutdown()
            print("\nYaya：下次见！")
            return

        if text == "/pause" or text.startswith("/pause "):
            if voice is None:
                print("请使用语音版启动入口。")
            elif text == "/pause":
                print(f"普通聊天停顿等待：{voice.pause_seconds:g}秒；用 /pause 3 调整。")
            else:
                try:
                    voice.set_pause(text.removeprefix("/pause ").strip())
                    print(f"普通聊天将等待约{voice.pause_seconds:g}秒停顿后结束；本次运行有效。")
                except ValueError:
                    print("停顿等待时间需要是1到5秒，例如 /pause 3。")
            continue
        if text in {"/endpoint on", "/endpoint off"}:
            if voice is None:
                print("请使用语音版启动入口。")
            else:
                voice.auto_end = text == "/endpoint on"
                print("人声检测自动结束已开启。" if voice.auto_end else "已切回手动结束录音。")
            continue
        if text in {"/review on", "/review off"}:
            review_transcript = text == "/review on"
            print("识别文字手动确认已开启。" if review_transcript else "识别后将直接发送。")
            continue
        if text in {"/voice on", "/voice off"}:
            if voice is None:
                print("请使用 run_voice_simulator.cmd 启动语音版。")
            else:
                voice.enabled = text == "/voice on"
                print("回答朗读已开启。" if voice.enabled else "回答朗读已关闭。")
            continue
        if text == "/listen":
            if voice is None:
                print("请使用 run_voice_simulator.cmd 启动语音版。")
                continue
            if yaya.session_status().muted:
                print("麦克风已静音，请先输入 /unmute；没有开启录音。")
                continue
            if latest_pending_id is not None:
                print("请先输入 /yes 或 /no 处理待确认记忆；没有开启录音。")
                continue
            try:
                token = CancellationToken()
                with cancel_on_ctrl_c(token):
                    recognized = voice.listen(token)
                print(f"识别结果：{recognized}")
                text = recognized.strip()
                if review_transcript:
                    confirmed = input("回车发送；输入新文字修正；输入 /cancel 放弃：").strip()
                    if confirmed == "/cancel":
                        continue
                    text = confirmed or text
                from_voice = True
                # Speech must never dispatch a management/destructive command.
                if text.startswith("/"):
                    print("语音确认不执行管理命令，请在主输入行手动输入。")
                    continue
            except (DialogueCancelled, KeyboardInterrupt):
                print("已取消语音输入，没有发送或保存。")
                continue
            except EOFError:
                yaya.shutdown()
                return
            except Exception as error:
                print(f"语音输入失败：{error}；仍可输入文字聊天。")
                continue
        if not text:
            continue
        if text == "/quit":
            yaya.shutdown()
            print("Yaya：下次见！")
            return
        if text == "/help":
            print(HELP)
            continue
        if text == "/clearhistory":
            yaya.clear_history()
            print("Yaya：短期对话历史已清空，长期记忆和成长值保留。")
            continue
        if text in {"/yes", "/no"}:
            if latest_pending_id is None:
                print("Yaya：现在没有等待确认的记忆。")
                continue
            approved = text == "/yes"
            handled = yaya.confirm_memory(latest_pending_id, approved)
            if handled:
                print("Yaya：我记住了！" if approved else "Yaya：好的，我不会保存。")
                latest_pending_id = None
            else:
                print("Yaya：这条记忆已经不存在了。")
            continue
        if text in {"/memory", "/memories"}:
            memories = yaya.list_memories()
            if not memories:
                print("Yaya：我还没有保存长期记忆。")
            for position, item in enumerate(memories, start=1):
                print(f"{position}. [{item.category}] {item.content}")
            if memories:
                print("      输入 /forget 编号 可以删除对应记忆。")
            continue
        if text.startswith("/forget "):
            memories = yaya.list_memories()
            reference = text.removeprefix("/forget ")
            memory_id = resolve_memory_id(reference, memories)
            deleted = memory_id is not None and yaya.delete_memory(memory_id)
            print(
                "Yaya：已经忘记了。"
                if deleted
                else "Yaya：没有找到这个编号对应的记忆。"
            )
            continue
        if text == "/forget":
            print("Yaya：请先用 /memory 查看编号，再输入 /forget 编号。")
            continue
        if text == "/growth":
            state = yaya.growth_state()
            skills = "、".join(state.unlocked_skills) or "暂无"
            print(
                f"互动次数：{state.interaction_count}；"
                f"成长值：{state.growth_points}；已解锁：{skills}"
            )
            continue
        if text == "/model":
            status = yaya.dialogue_status()
            print(
                f"对话模式：{status.mode}；"
                f"当前引擎：{status.active_provider}；"
                f"模型：{status.model or '未配置'}；"
                f"模型服务配置：{'是' if status.configured else '否'}"
            )
            if status.last_error:
                print(f"最近降级原因：{status.last_error}")
            continue
        if text == "/status":
            status = yaya.session_status()
            print(
                f"会话状态：{status.state.value}；"
                f"静音：{'是' if status.muted else '否'}；"
                f"网络：{'在线' if status.online else '离线'}；"
                f"电量：{status.battery_percent}%"
            )
            if status.last_error:
                print(f"最近错误：{status.last_error}")
            continue
        if text == "/mute":
            yaya.set_muted(True)
            print("Yaya：麦克风已静音，管理命令仍然可以使用。")
            continue
        if text == "/unmute":
            yaya.set_muted(False)
            print("Yaya：麦克风已恢复。")
            continue
        if text == "/offline":
            yaya.set_online(False)
            print("Yaya：网络已断开，我会继续使用本地规则。")
            continue
        if text == "/online":
            yaya.set_online(True)
            print("Yaya：网络已恢复。")
            continue
        if text.startswith("/battery "):
            raw_percent = text.removeprefix("/battery ").strip()
            try:
                percent = int(raw_percent)
            except ValueError:
                print("Yaya：电量需要是 0 到 100 之间的整数。")
                continue
            status = yaya.set_battery(percent)
            print(f"Yaya：虚拟电量已设为 {status.battery_percent}%。")
            if status.battery_percent <= 20:
                print("      低电保护已启用，移动动作将被替换为静止。")
            continue
        if text == "/battery":
            print("Yaya：请输入电量，例如 /battery 10。")
            continue
        if text == "/touch":
            yaya.touch()
            continue
        if text == "/collision":
            yaya.collision()
            print("Yaya：检测到碰撞，当前行为已停止。")
            continue
        if text == "/interrupt":
            yaya.interrupt()
            print("Yaya：当前回复或任务已打断。")
            continue
        if text == "/events":
            events = yaya.event_history()[-10:]
            if not events:
                print("Yaya：目前还没有事件记录。")
            for event in events:
                print(
                    f"- {event.occurred_at.astimezone():%H:%M:%S} "
                    f"{event.type.value}"
                )
            continue
        if text == "/reset yes":
            yaya.reset_state()
            latest_pending_id = None
            print("Yaya：长期记忆和成长状态已经全部清除。")
            continue
        if text == "/reset":
            print("Yaya：这会清除全部记忆和成长状态。确认请输入 /reset yes")
            continue

        if latest_pending_id is not None and not text.startswith("/"):
            try:
                token = CancellationToken()
                with cancel_on_ctrl_c(token):
                    decision = yaya.interpret_confirmation(latest_pending_id, text, token)
                if decision.intent in {"approve", "reject"}:
                    approved = decision.intent == "approve"
                    handled = yaya.confirm_memory(latest_pending_id, approved)
                    latest_pending_id = None
                    print("Yaya：" + (("我记住了！" if approved else "好的，我不会保存。") if handled else "待确认记忆已不存在。"))
                elif decision.intent == "revise":
                    print(f"Yaya：改为记住『{decision.content}』。可以保存吗？")
                else:
                    print("Yaya：你同意保存刚才那条记忆吗？可说可以啊，或不要；也可输入 /yes 或 /no。")
            except (DialogueCancelled, KeyboardInterrupt):
                print("确认已取消，尚未保存；可用 /no 放弃候选。")
            continue

        try:
            token = CancellationToken()
            with cancel_on_ctrl_c(token):
                result = yaya.interact(text, on_text=console.preview, cancellation=token)
        except DialogueCancelled as error:
            console.abort_preview()
            print(f"Yaya：{error}")
            continue
        except InteractionBlockedError as error:
            print(f"Yaya：{error}")
            continue
        except Exception as error:
            console.abort_preview()
            print(f"Yaya：刚才出现了问题：{error}")
            print("      管理命令仍然可用，可输入 /status 查看状态。")
            continue
        if result.pending_memory_id is not None:
            latest_pending_id = result.pending_memory_id
            print("      输入 /yes 保存，输入 /no 放弃。")
        if voice is not None and voice.enabled:
            auto_confirm = from_voice and result.pending_memory_id is not None
            try:
                print("正在朗读，Ctrl+C 可停止朗读。", flush=True)
                # Playback is a separate stage: the completed text is already committed.
                playback_token = CancellationToken()
                with cancel_on_ctrl_c(playback_token):
                    speech = result.speech
                    if auto_confirm:
                        speech += " 提示音后请说记住吧，或者不要。"
                    voice.speak(speech, playback_token)
                    playback_token.check()
            except (DialogueCancelled, KeyboardInterrupt):
                print("朗读已停止；已完成的文字回复和成长记录保留。")
                continue
            except Exception as error:
                print(f"朗读失败：{error}；文字回复已保留，可用 /voice off 关闭朗读。")
                continue
            if auto_confirm:
                confirm_by_voice(yaya, voice, latest_pending_id)
                latest_pending_id = None


if __name__ == "__main__":
    main()

