# Two-minute rules-only demonstration

This walkthrough demonstrates the memory approval workflow using synthetic example information. It needs no robot, microphone, model download or network service. Follow [RUNNING.md](RUNNING.md) to create a fresh virtual environment first. Run in a fresh checkout so the demonstration does not mix with personal memory data.

From `software/` in PowerShell:

```powershell
$env:PET_YAYA_DIALOGUE_MODE = "rules"
.\.venv\Scripts\python.exe -X utf8 launch_simulator.py
```

At the simulator prompt, enter these commands one at a time:

```text
请记住，我喜欢恐龙
/memory
/yes
/memory
/quit
```

| Step | What to inspect |
| --- | --- |
| Propose the example fact | A memory proposal should await approval |
| First `/memory` | The new fact should not yet be in confirmed memory |
| `/yes` | Approve the pending proposal |
| Second `/memory` | The confirmed fact should be listed |
| Restart and enter `/memory` | Check persistence across sessions |

These are expected observations, not a captured transcript. Exact response text can vary. To remove the example, use `/forget` with its displayed list number. Do not reset an existing personal database. The rules-only demo checks application behavior; it does not demonstrate open-ended model dialogue or speech accuracy.

See [TESTING.md](TESTING.md) for recorded tests and the optional model/voice demonstration.

---

## 中文说明

先按照运行指南准备独立环境，在新检出目录中启动规则模式，依次提出“我喜欢恐龙”的记忆请求、查看未批准状态、批准后再次查看，再重启验证持久化。上表是预期观察，不是假装录制的运行日志。完成后按列表编号删除这条示例记忆，不重置已有个人数据库。
