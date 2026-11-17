// Test the shipped module against the documented Claude Mod API, without a client.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
const source = await readFile(new URL('../plugins/claude-update/hooks/register.js', import.meta.url), 'utf8')
const { register, displayText } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)
const base = {
  schema_version: 1, task_id: 'task-one', result: 'running', stage: 'downloading',
  from_version: '0.3.0', to_version: '0.4.0', finished_at: null,
}
let checks = 0
function check(condition, message) { assert.ok(condition, message); checks++ }
function harness(env = { HOME: '/fixture', AGENTDEV_HOME: '/fixture/installation' }) {
  let now = 100_000
  let state = JSON.stringify(base)
  const events = new Map(), timers = [], rendered = [], reads = []
  let turns = 0
  const timer = (delay, fn, repeat) => {
    const value = { delay, fn, repeat, due: now + delay, cancelled: false, cancel() { this.cancelled = true } }
    timers.push(value)
    return value
  }
  const api = {
    env: { get: async key => env[key], set: async (key, value) => { env[key] = value; return {} } },
    session: { cwd: async () => '/fixture/project/subdir' },
    fs: {
      read: async path => {
        reads.push(path)
        if (path.endsWith('agentskill-path')) {
          if (!env.POINTER || !path.includes('/project/agent-workspace')) throw Error('missing pointer')
          return env.POINTER
        }
        if (state === null) throw Error('missing file')
        return state
      },
      exists: async path => path.endsWith('/.agentdev-app'),
    },
    clock: {
      now: async () => now,
      every: (delay, fn) => timer(delay, fn, true),
      after: (delay, fn) => timer(delay, fn, false),
    },
    ui: { status: value => rendered.push(value) },
  }
  register((event, callback) => events.set(event, callback))
  const settle = async () => { for (let i = 0; i < 30; i++) await Promise.resolve() }
  return {
    rendered, timers, env, reads,
    setState(value) { state = typeof value === 'object' && value !== null ? JSON.stringify(value) : value },
    async start() { await events.get('session.start')(api, {}, event => { turns++; return event }); await settle() },
    async end() { await events.get('session.end')(api, {}, event => event); await settle() },
    async at(time) {
      now = time
      for (const value of [...timers]) {
        if (value.cancelled || value.due > now) continue
        if (value.repeat) value.due = now + value.delay
        else value.cancelled = true
        await value.fn()
      }
      await settle()
    },
    turns: () => turns,
  }
}

check(displayText(base, 100).includes('下载源码'), 'renders progress')
check(displayText({ ...base, result: 'success', finished_at: 100 }, 109).includes('更新成功'), 'keeps result before expiry')
check(displayText({ ...base, result: 'failed', finished_at: 100 }, 110) === undefined, 'expires exactly at completion + 10s')
check(displayText({ ...base, result: 'blocked', finished_at: 100, error: '异常改动' }, 101).includes('异常改动'), 'renders risk')
check(displayText({ ...base, schema_version: 2 }, 100) === undefined, 'rejects unknown schema')
check(displayText({ ...base, result: 'success', finished_at: null }, 100) === undefined, 'rejects invalid completion')

const h = harness()
await h.start()
check(h.turns() === 1, 'does not request another chat turn')
check(h.rendered.at(-1).includes('下载源码'), 'renders before any prompt')
check(h.env.AGENTDEV_CLIENT === 'claude', 'routes children to plugin')
check(h.reads.includes('/fixture/installation/update-status.json'), 'reads outside app')
h.setState({ ...base, result: 'success', finished_at: 100 })
await h.at(101_000)
check(h.rendered.at(-1).includes('更新成功'), 'observes background completion while idle')
await h.at(109_999)
check(h.rendered.at(-1).includes('更新成功'), 'result remains until its expiry')
await h.at(110_000)
check(h.rendered.at(-1) === undefined, 'clears only plugin status, not native user settings')

const late = harness()
late.setState({ ...base, result: 'failed', finished_at: 80 })
await late.start()
check(late.rendered.length === 0, 'old completion does not reappear in a new session')

const newer = harness()
newer.setState({ ...base, result: 'failed', finished_at: 100 })
await newer.start()
newer.setState({ ...base, task_id: 'task-two', stage: 'dependencies' })
await newer.at(105_000)
await newer.at(110_000)
check(newer.rendered.at(-1).includes('安装依赖'), 'old cleanup timer cannot erase a new task')
await newer.end()
check(newer.rendered.at(-1) === undefined, 'session end clears plugin status')
check(newer.timers.every(t => t.cancelled), 'session end stops timers')
const count = newer.rendered.length
await newer.at(120_000)
check(newer.rendered.length === count, 'ended session cannot repaint')

const invalid = harness()
invalid.setState('{')
await invalid.start()
invalid.setState(null)
await invalid.at(101_000)
check(invalid.turns() === 1 && invalid.rendered.length === 0, 'missing or corrupt JSON does not break the client')
invalid.setState(base)
await invalid.at(102_000)
check(invalid.rendered.at(-1).includes('下载源码'), 'poll recovers from read failure')
await invalid.start()
check(invalid.timers.filter(t => t.repeat && !t.cancelled).length === 1, 'restarting session does not leak polling timers')

const pointer = harness({ HOME: '/fixture', POINTER: '/custom/install/app' })
await pointer.start()
check(pointer.reads.includes('/custom/install/update-status.json'), 'discovers custom installation through project pointer')
const tilde = harness({ HOME: '/fixture', AGENTDEV_HOME: '~/custom' })
await tilde.start()
check(tilde.reads.includes('/fixture/custom/update-status.json'), 'expands explicit tilde home')

console.log(`Claude plugin: ${checks} assertions passed (API test double; not real UI acceptance)`)
console.log('底部提示示例：' + displayText(base, 100))
console.log('完成提示示例：' + displayText({ ...base, result: 'success', finished_at: 100 }, 101))
console.log('完成 10 秒后：' + String(displayText({ ...base, result: 'success', finished_at: 100 }, 110)))
