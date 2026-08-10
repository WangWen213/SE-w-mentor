export type NavKey =
  | "workbench"
  | "tasks"
  | "memory"
  | "governance"
  | "evaluation"
  | "settings";

export type TaskTab = "conversation" | "changes" | "checks";

export type BadgeTone = "allow" | "warn" | "block" | "neutral" | "info";

export interface MessageFixture {
  id: string;
  author: "mentor" | "user";
  body: string;
  time: string;
}

export interface ProposalFixture {
  goal: string;
  items: string[];
  files: string;
  risk: string;
}

export interface TaskFixture {
  title: string;
  status: string;
  messages: MessageFixture[];
  proposal: ProposalFixture;
  changes: Array<{
    file: string;
    state: string;
    added: number;
    removed: number;
  }>;
  checks: Array<{
    label: string;
    state: string;
    tone: BadgeTone;
  }>;
}

export const navItems: Array<{
  key: NavKey;
  label: string;
  marker: string;
  count?: string;
}> = [
  { key: "workbench", label: "工作台", marker: "W" },
  { key: "tasks", label: "任务", marker: "T", count: "6" },
  { key: "memory", label: "记忆", marker: "M" },
  { key: "governance", label: "治理", marker: "G", count: "1" },
  { key: "evaluation", label: "评估", marker: "E" },
  { key: "settings", label: "设置", marker: "S" },
];

export const taskFixture: TaskFixture = {
  title: "为用户模块增加 email 字段",
  status: "等待你确认",
  messages: [
    {
      id: "m1",
      author: "user",
      body: "给用户模块增加 email 字段，并补充测试。",
      time: "15:02",
    },
    {
      id: "m2",
      author: "mentor",
      body: "可以。我先把这次修改范围整理给你确认。",
      time: "15:02",
    },
  ],
  proposal: {
    goal: "增加用户 email 字段",
    items: ["同步接口校验", "补充相关测试"],
    files: "4 个文件",
    risk: "无高风险操作",
  },
  changes: [
    { file: "models/user.py", state: "已修改", added: 4, removed: 1 },
    { file: "schemas/user.py", state: "已修改", added: 6, removed: 0 },
    { file: "services/user_service.py", state: "已修改", added: 3, removed: 1 },
    { file: "tests/test_user.py", state: "已修改", added: 12, removed: 0 },
  ],
  checks: [
    { label: "需求是否满足", state: "等待", tone: "neutral" },
    { label: "相关测试", state: "等待", tone: "neutral" },
    { label: "修改是否超出范围", state: "等待", tone: "neutral" },
    { label: "是否还有待处理确认", state: "需要确认", tone: "warn" },
  ],
};

export const cards = {
  tasks: [
    ["给订单接口补充分页", "已完成", "done"],
    ["更新认证中间件", "需要授权", "review"],
    ["优化登录流程", "需要补充", "review"],
  ],
  memory: [
    ["项目经验", "用户模块字段变化需要同步 schema 与 service 测试。", "已验证"],
    ["近期决策", "公共接口变化需要先确认影响范围。", "需复核"],
  ],
  policies: [
    ["允许", "读取项目文件、搜索代码、运行已配置测试"],
    ["需要确认", "公共接口变化、数据库迁移、安装依赖"],
    ["阻止", "访问项目外文件、读取密钥、绕过测试"],
  ],
};
