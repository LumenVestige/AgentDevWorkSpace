// No Node imports or global timers: this module runs in Claude Code's Mod sandbox.
const stages = {
  checking: '检查安装目录', downloading: '下载源码', dependencies: '安装依赖',
  validating: '验证运行环境', staging: '准备安装文件', activating: '切换安装',
  refreshing: '刷新工作区',
}
const results = { success: '更新成功', failed: '更新失败', blocked: '更新已暂停' }
const clean = value => String(value ?? '').replace(/[\x00-\x1f\x7f]/g, ' ').slice(0, 300)

export function displayText(state, now) {
  if (!state || state.schema_version !== 1 || typeof state.task_id !== 'string') return undefined
  if (state.result === 'running') {
    return `AgentDevWorkSpace · ${stages[state.stage] || '更新中'} · ${clean(state.from_version)} → ${clean(state.to_version) || '未知'}`
  }
  if (!results[state.result] || !Number.isFinite(state.finished_at) || now >= state.finished_at + 10) return undefined
  const reason = state.error ? ` · ${clean(state.error)}` : ''
  return `AgentDevWorkSpace · ${results[state.result]} · ${clean(state.to_version) || '未知'}${reason}`
}

async function installationHome($) {
  const override = await $.env.get('AGENTDEV_HOME')
  const home = await $.env.get('HOME')
  if (override) return override.replace(/^~(?=\/|$)/, home || '~').replace(/\/$/, '')
  // Custom installations are discoverable from the project's existing pointer.
  let cwd = await $.session.cwd()
  while (cwd) {
    try {
      const app = (await $.fs.read(`${cwd}/agent-workspace/.agent/env/agentskill-path`)).trim()
      if (app.endsWith('/app') && await $.fs.exists(`${app}/.agentdev-app`)) return app.slice(0, -4)
    } catch { /* A session need not belong to an initialized project. */ }
    const parent = cwd.slice(0, cwd.lastIndexOf('/'))
    if (parent === cwd) break
    cwd = parent
  }
  return home ? `${home}/.agent-dev-workspace` : undefined
}

export function register(on) {
  let stop = () => {}
  on('session.start', async ($, e, next) => {
    stop()
    let stopped = false
    let busy = false
    let shown
    let taskId
    let expiry
    let clearTimer
    let pollTimer
    stop = () => {
      stopped = true
      pollTimer?.cancel()
      clearTimer?.cancel()
      $.ui.status(undefined)
    }
    const pathHome = await installationHome($)
    // Hook-launched background processes inherit the client route; explicit hook
    // --client arguments still win when another client uses the same project.
    await $.env.set('AGENTDEV_CLIENT', 'claude')
    const publish = text => {
      if (!stopped && text !== shown) {
        shown = text
        $.ui.status(text)
      }
    }
    const poll = async () => {
      if (stopped || busy || !pathHome) return
      busy = true
      try {
        const state = JSON.parse(await $.fs.read(`${pathHome}/update-status.json`))
        const now = (await $.clock.now()) / 1000
        if (stopped) return
        publish(displayText(state, now))
        const nextExpiry = state.result === 'running' ? undefined : state.finished_at + 10
        if (taskId !== state.task_id || expiry !== nextExpiry) {
          taskId = state.task_id
          expiry = nextExpiry
          clearTimer?.cancel()
          // Use the writer's completion time, not the first time this session
          // observes it. An old completion must never reappear on restart.
          if (Number.isFinite(expiry) && expiry > now) {
            const expected = taskId
            clearTimer = $.clock.after((expiry - now) * 1000, () => {
              if (!stopped && taskId === expected) publish(undefined)
            })
          }
        }
      } catch { publish(undefined) /* Do not leave stale progress on a broken state file. */ }
      finally { busy = false }
    }
    pollTimer = $.clock.every(1000, poll)
    void poll()
    return next(e)
  })
  on('session.end', ($, e, next) => {
    stop()
    return next(e)
  })
}
