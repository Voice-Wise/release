// 发布候选验证矩阵。汇总本仓本地验收、Release 仓打包目标和剩余风险。
import { buildElectronWorkflowPlan } from './workflow-contract.mjs'

export const LOCAL_VALIDATION_COMMANDS = [
  'npm run typecheck',
  'npm run test',
  'npm run test:functional:local',
  'npm run build'
]

export const RELEASE_CANDIDATE_CHECKS = [
  {
    id: 'typecheck',
    layer: 'local',
    command: 'npm run typecheck',
    required: true
  },
  {
    id: 'unit',
    layer: 'local',
    command: 'npm run test',
    required: true
  },
  {
    id: 'functional-local',
    layer: 'local',
    command: 'npm run test:functional:local',
    required: true
  },
  {
    id: 'build',
    layer: 'local',
    command: 'npm run build',
    required: true
  },
  {
    id: 'native-smoke',
    layer: 'native',
    command: 'npm run test:native-smoke',
    required: false,
    riskIfMissing: '真实系统权限、热键、粘贴和前台应用能力仍需在 macOS/Windows 机器上做 native smoke。'
  }
]

export function buildReleaseCandidatePlan({ skipWindows = true } = {}) {
  const workflow = buildElectronWorkflowPlan({ skipWindows })
  return {
    localValidation: LOCAL_VALIDATION_COMMANDS.join(' && '),
    checks: RELEASE_CANDIDATE_CHECKS,
    releaseWorkflow: {
      repositories: workflow.repositories,
      dispatchContracts: workflow.dispatchContracts,
      packageTargets: workflow.commands.package,
      manifestCommand: workflow.commands.manifest,
      secretTodos: workflow.secrets.missingTodo
    }
  }
}

export function evaluateReleaseCandidateResults(results, { skipWindows = true } = {}) {
  const resultById = new Map(results.map((result) => [result.id, result]))
  const failedRequired = []
  const missingRequired = []
  const risks = []

  for (const check of RELEASE_CANDIDATE_CHECKS) {
    const result = resultById.get(check.id)
    if (!result) {
      if (check.required) missingRequired.push(check.id)
      else if (check.riskIfMissing) risks.push(check.riskIfMissing)
      continue
    }
    if (result.status !== 'pass' && check.required) failedRequired.push(check.id)
    if (result.status !== 'pass' && !check.required && check.riskIfMissing) risks.push(check.riskIfMissing)
  }

  const plan = buildReleaseCandidatePlan({ skipWindows })
  for (const todo of plan.releaseWorkflow.secretTodos) risks.push(todo.reason)

  return {
    status: failedRequired.length || missingRequired.length ? 'blocked' : risks.length ? 'validated-with-risks' : 'validated',
    failedRequired,
    missingRequired,
    risks
  }
}
