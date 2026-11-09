import commandProtocol from '../../protocol/client_commands.json'

const CLIENT_COMMANDS = [
  'agent.run',
  'task.cancel',
  'session.reset',
  'voice.start',
  'voice.stop',
  'voice.text.query',
  'voice.mic.open',
  'voice.mic.close',
  'voice.playback.ended',
] as const

type CommandDescriptor = {
  command: (typeof CLIENT_COMMANDS)[number]
  payload: string | null
  success_status: 'accepted' | 'completed'
}

type ClientCommandProtocol = {
  protocol_version: number
  commands: CommandDescriptor[]
}

const CLIENT_COMMAND_PROTOCOL = commandProtocol as ClientCommandProtocol

export const PROTOCOL_VERSION = CLIENT_COMMAND_PROTOCOL.protocol_version
export type AgentCommand = (typeof CLIENT_COMMANDS)[number]

export const RUNTIME_CLIENT_COMMANDS = Object.freeze(
  CLIENT_COMMAND_PROTOCOL.commands.map(({ command }) => command),
) as readonly AgentCommand[]

const declaredCommands = new Set<string>(CLIENT_COMMANDS)
const runtimeCommands = new Set<string>(RUNTIME_CLIENT_COMMANDS)
if (
  declaredCommands.size !== CLIENT_COMMANDS.length
  || runtimeCommands.size !== RUNTIME_CLIENT_COMMANDS.length
  || declaredCommands.size !== runtimeCommands.size
  || CLIENT_COMMANDS.some((command) => !runtimeCommands.has(command))
) {
  throw new Error('Client command literals do not match the JSON protocol descriptor.')
}
