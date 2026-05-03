// Electron Release workflow 合同。描述私有仓 dispatch 与公有 Release 仓 Electron CI/发布命令。
import { buildElectronPackageMatrix } from './package-matrix.mjs'

export const SOURCE_REPOSITORY = 'Voice-Wise/voicewise-electron'
export const RELEASE_REPOSITORY = 'Voice-Wise/release'

export const DISPATCH_CONTRACTS = [
  {
    eventType: 'ci',
    sourceWorkflow: '.github/workflows/trigger-ci.yml',
    releaseWorkflow: '.github/workflows/ci.yml',
    requiredPayloadKeys: ['sha', 'ref', 'skip_windows', 'sender_repo']
  },
  {
    eventType: 'nightly',
    sourceWorkflow: '.github/workflows/trigger-nightly.yml',
    releaseWorkflow: '.github/workflows/nightly.yml',
    requiredPayloadKeys: ['ref', 'branch', 'skip_windows']
  },
  {
    eventType: 'release',
    sourceWorkflow: '.github/workflows/trigger-release.yml',
    releaseWorkflow: '.github/workflows/release.yml',
    requiredPayloadKeys: ['ref', 'version', 'skip_windows']
  }
]

export const RELEASE_SECRET_CONTRACT = {
  required: [
    'PRIVATE_REPO_TOKEN',
    'DASHSCOPE_API_KEY',
    'VOICEWISE_TEST_AUTH_JSON',
    'APPLE_CERTIFICATE',
    'APPLE_CERTIFICATE_PASSWORD',
    'APPLE_SIGNING_IDENTITY',
    'APPLE_ID',
    'APPLE_PASSWORD',
    'APPLE_TEAM_ID',
    'SENTRY_AUTH_TOKEN',
    'SENTRY_ORG',
    'SENTRY_PROJECT'
  ],
  missingTodo: [
    {
      key: 'WINDOWS_CODE_SIGNING_CERTIFICATE',
      reason: 'Release 仓现有 YAML 未提供 Windows 签名证书；skip_windows=false 前必须补齐或显式 unsigned 降级。'
    }
  ]
}

const FORBIDDEN_TAURI_COMMANDS = [
  'bun run test:rust',
  'bun run test:functional',
  'tauri-apps/tauri-action',
  'src-tauri/target'
]

export function normalizeSkipWindows(value) {
  return ['true', '1', 'yes'].includes(String(value ?? 'true').trim().toLowerCase())
}

export function validateDispatchPayload(eventType, payload) {
  const contract = DISPATCH_CONTRACTS.find((item) => item.eventType === eventType)
  if (!contract) throw new Error(`Unknown dispatch event type: ${eventType}`)

  const missing = contract.requiredPayloadKeys.filter((key) => !(key in payload))
  if (missing.length) {
    throw new Error(`Missing ${eventType} payload keys: ${missing.join(', ')}`)
  }

  if (typeof payload.skip_windows !== 'boolean') {
    throw new Error(`${eventType} payload skip_windows must be boolean`)
  }

  return {
    eventType,
    sourceWorkflow: contract.sourceWorkflow,
    releaseWorkflow: contract.releaseWorkflow,
    skipWindows: payload.skip_windows
  }
}

export function buildElectronWorkflowPlan({ skipWindows = true } = {}) {
  const packageMatrix = buildElectronPackageMatrix({ skipWindows })
  const install = 'bun install --frozen-lockfile'
  const validation = ['npm run typecheck', 'npm run test', 'npm run test:functional:local']
  const build = 'npm run build'

  return {
    repositories: {
      source: SOURCE_REPOSITORY,
      release: RELEASE_REPOSITORY
    },
    dispatchContracts: DISPATCH_CONTRACTS,
    secrets: RELEASE_SECRET_CONTRACT,
    commands: {
      install,
      validation,
      build,
      package: packageMatrix.include.map((item) => ({
        name: item.name,
        os: item.os,
        platform: item.platform,
        arch: item.arch,
        command: `npm run build && electron-builder ${item.builderArgs}`,
        artifactName: item.artifactName,
        artifactPaths: item.artifactPaths
      })),
      manifest: 'node electron-release/generate-updater-manifest.mjs'
    },
    forbiddenTauriCommands: FORBIDDEN_TAURI_COMMANDS
  }
}

export function assertElectronWorkflowPlan(plan) {
  const serialized = JSON.stringify(plan.commands)
  const forbidden = FORBIDDEN_TAURI_COMMANDS.filter((command) => serialized.includes(command))
  if (forbidden.length) {
    throw new Error(`Electron workflow plan still contains Tauri commands: ${forbidden.join(', ')}`)
  }
  if (!serialized.includes('electron-builder')) {
    throw new Error('Electron workflow plan must package with electron-builder')
  }
  return true
}
