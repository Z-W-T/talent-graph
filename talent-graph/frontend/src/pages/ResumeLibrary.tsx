import { Button, Card, Checkbox, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { STATUS_MAP, displayName, resumeApi, type Resume } from "../api/client";

const STATUS_OPTIONS = Object.entries(STATUS_MAP).map(([value, v]) => ({ value, label: v.label }));
const SCALAR_EDIT_FIELDS = ["name", "education", "major", "age", "phone", "email", "research", "intention"];
const FIELD_LABELS: Record<string, string> = {
  name: "姓名", education: "学历", major: "专业", age: "年龄",
  phone: "电话", email: "邮箱", research: "研究方向", intention: "个人意愿概述",
  work_history: "工作履历摘要", work_experiences: "工作经历", achievements: "科研成果",
};
const ACH_LABELS: Record<string, string> = {
  papers: "论文/著作", patents: "专利", projects: "科研项目", awards: "人才称号/获奖",
};
// 个人意愿拆分项
const INTENTION_LABELS: Record<string, string> = {
  city: "期望地点", salary: "期望薪酬", status: "工作状态", reason: "跳槽原因",
};

const isParsing = (r: Resume) => !!(r.confidence || {})._parsing;
const parseError = (r: Resume) => (r.confidence || {})._error as string | undefined;

// 科研成果类型选项（存储键 -> 展示名）
const ACH_TYPE_OPTIONS = [
  { value: "papers", label: "文章" },
  { value: "patents", label: "专利" },
  { value: "projects", label: "项目" },
  { value: "awards", label: "奖项" },
];
/** 科研成果对象 -> 表格行 [{type, detail}] */
const flattenAchievements = (ach: any): { type: string; detail: string }[] => {
  if (!ach || typeof ach !== "object") return [];
  return ACH_TYPE_OPTIONS.flatMap(({ value }) =>
    (Array.isArray(ach[value]) ? ach[value] : []).map((detail: string) => ({ type: value, detail }))
  );
};
/** 表格行 -> 科研成果对象 {papers:[...],...}，空行忽略 */
const groupAchievements = (rows: { type?: string; detail?: string }[] = []): Record<string, string[]> => {
  const out: Record<string, string[]> = {};
  for (const row of rows) {
    const detail = (row?.detail || "").trim();
    if (!detail) continue;
    const type = ACH_TYPE_OPTIONS.some((o) => o.value === row.type) ? (row.type as string) : "papers";
    (out[type] ||= []).push(detail);
  }
  return out;
};

export default function ResumeLibraryPage() {
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<string>();
  const [lowConfOnly, setLowConfOnly] = useState(false);
  const [editing, setEditing] = useState<Resume>();
  const [form] = Form.useForm();

  const refresh = () =>
    resumeApi
      .list({ keyword, status, low_confidence_only: lowConfOnly })
      .then((r) => setResumes(r.data));
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 8000); // 轮询，解析完成后自动刷新状态
    return () => clearInterval(t);
  }, [status, lowConfOnly]);

  const openEdit = (r: Resume) => {
    setEditing(r);
    const detail = r.structured?.intention_detail || {};
    form.setFieldsValue({
      ...Object.fromEntries(SCALAR_EDIT_FIELDS.map((f) => [f, r.structured?.[f]])),
      work_history: r.structured?.work_history,
      intention_city: detail.city,
      intention_salary: detail.salary,
      intention_status: detail.status,
      intention_reason: detail.reason,
      // 工作经历：表格式编辑，直接使用数组
      work_experiences: Array.isArray(r.structured?.work_experiences) ? r.structured.work_experiences : [],
      // 科研成果：把 {papers:[...],patents:[...],...} 拍平成 [{type, detail}] 供表格编辑
      achievements_list: flattenAchievements(r.structured?.achievements),
    });
  };

  const saveEdit = async () => {
    if (!editing) return;
    const values = await form.validateFields();
    const structured: Record<string, any> = {};
    SCALAR_EDIT_FIELDS.forEach((f) => {
      if (values[f] !== undefined && values[f] !== "") structured[f] = values[f];
    });
    if (values.age !== undefined && values.age !== "") structured.age = Number(values.age) || values.age;
    if (values.work_history) structured.work_history = values.work_history;
    // 个人意愿拆分项
    const intentionDetail = {
      city: values.intention_city || null,
      salary: values.intention_salary || null,
      status: values.intention_status || null,
      reason: values.intention_reason || null,
    };
    if (Object.values(intentionDetail).some((v) => v)) structured.intention_detail = intentionDetail;
    // 工作经历：表格行 -> 数组，忽略全空行
    const exps = (values.work_experiences || [])
      .map((e: any) => ({
        company: (e?.company || "").trim(),
        title: (e?.title || "").trim(),
        period: (e?.period || "").trim(),
        description: (e?.description || "").trim(),
      }))
      .filter((e: any) => e.company || e.title || e.period || e.description);
    structured.work_experiences = exps;
    // 科研成果：表格行 -> {papers/patents/projects/awards}
    structured.achievements = groupAchievements(values.achievements_list);
    await resumeApi.update(editing.id, { structured });
    message.success("已保存修正，向量已重新生成");
    setEditing(undefined);
    refresh();
  };

  const removeResume = async (r: Resume) => {
    await resumeApi.remove(r.id);
    message.success(`已删除简历「${displayName(r)}」`);
    refresh();
  };

  const lowConfFields = (r: Resume) =>
    Object.entries(r.confidence || {})
      .filter(([k, v]) => typeof v === "number" && v < 0.7)
      .map(([k]) => FIELD_LABELS[k] || k);

  const columns = [
    { title: "姓名", width: 100, render: (_: unknown, r: Resume) => displayName(r) },
    { title: "学历", width: 80, render: (_: unknown, r: Resume) => r.structured?.education || "-" },
    { title: "专业", width: 150, render: (_: unknown, r: Resume) => r.structured?.major || "-" },
    {
      title: "年龄",
      width: 110,
      render: (_: unknown, r: Resume) =>
        r.structured?.age ? `${r.structured.age} 岁` : "-",
    },
    {
      title: "研究方向",
      ellipsis: true,
      render: (_: unknown, r: Resume) => r.structured?.research || "-",
    },
    { title: "渠道", dataIndex: "source", width: 100 },
    {
      title: "状态",
      dataIndex: "status",
      width: 130,
      render: (v: string, r: Resume) => (
        <Select
          size="small"
          value={v}
          options={STATUS_OPTIONS}
          style={{ width: 110 }}
          onChange={(s) => resumeApi.update(r.id, { status: s }).then(refresh)}
        />
      ),
    },
    {
      title: "解析状态",
      width: 150,
      render: (_: unknown, r: Resume) => {
        if (isParsing(r)) return <Tag color="processing">解析中…</Tag>;
        const err = parseError(r);
        if (err) return <Tag color="error" title={err}>解析失败</Tag>;
        return lowConfFields(r).length ? (
          <Tag color="warning">{lowConfFields(r).join("、")} 待修正</Tag>
        ) : (
          <Tag color="success">正常</Tag>
        );
      },
    },
    {
      title: "操作",
      width: 200,
      render: (_: unknown, r: Resume) => (
        <Space size="small">
          <a onClick={() => openEdit(r)}>修正</a>
          {!isParsing(r) && (
            <a onClick={() => resumeApi.reparse(r.id).then(refresh).catch((e) => message.error(e?.response?.data?.detail || "重新解析失败"))}>
              重新解析
            </a>
          )}
          <Popconfirm
            title="删除简历"
            description={`确认删除「${displayName(r)}」？关联的匹配记录会一并删除，且不可恢复。`}
            okText="删除"
            okButtonProps={{ danger: true }}
            cancelText="取消"
            onConfirm={() => removeResume(r)}
          >
            <a style={{ color: "#ff4d4f" }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card title="简历库检索与标签管理">
      <Space style={{ marginBottom: 16 }} wrap>
        <Input.Search
          placeholder="姓名 / 专业 / 研究方向 / 技能"
          style={{ width: 280 }}
          onSearch={(v) => {
            setKeyword(v);
            resumeApi.list({ keyword: v, status, low_confidence_only: lowConfOnly }).then((r) => setResumes(r.data));
          }}
          allowClear
        />
        <Select placeholder="状态" allowClear style={{ width: 130 }} options={STATUS_OPTIONS}
          value={status} onChange={setStatus} />
        <Checkbox checked={lowConfOnly} onChange={(e) => setLowConfOnly(e.target.checked)}>
          只看待修正
        </Checkbox>
        <Button onClick={refresh}>刷新</Button>
        <span style={{ color: "#999" }}>共 {resumes.length} 份</span>
      </Space>

      <Table
        rowKey="id"
        size="small"
        columns={columns}
        dataSource={resumes}
        pagination={{ pageSize: 20 }}
        expandable={{
          rowExpandable: (r) => !isParsing(r),
          expandedRowRender: (r) => <ResumeDetail resume={r} />,
        }}
      />

      <Modal open={!!editing} title={`人工修正 · ${editing ? displayName(editing) : ""}`} onOk={saveEdit} width={860}
        onCancel={() => setEditing(undefined)} okText="保存" cancelText="取消">
        <AlertBanner resume={editing} />
        <Form form={form} layout="vertical">
          {SCALAR_EDIT_FIELDS.map((f) => (
            <Form.Item key={f} name={f} label={FIELD_LABELS[f]} style={{ marginBottom: 12 }}>
              <Input />
            </Form.Item>
          ))}
          <Form.Item name="work_history" label="工作履历摘要" style={{ marginBottom: 12 }}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Space size="small" wrap style={{ display: "flex", marginBottom: 12 }}>
            <Form.Item name="intention_city" label="期望地点" style={{ marginBottom: 0 }}>
              <Input style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="intention_salary" label="期望薪酬" style={{ marginBottom: 0 }}>
              <Input style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="intention_status" label="工作状态" style={{ marginBottom: 0 }}>
              <Input style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="intention_reason" label="跳槽原因" style={{ marginBottom: 0 }}>
              <Input style={{ width: 200 }} />
            </Form.Item>
          </Space>
          <Form.Item label="工作经历" style={{ marginBottom: 12 }}>
            <Form.List name="work_experiences">
              {(fields, { add, remove }) => (
                <div style={{ border: "1px solid #f0f0f0", borderRadius: 8, padding: 8 }}>
                  {fields.length > 0 && (
                    <div style={{ display: "flex", gap: 8, marginBottom: 4, color: "#888", fontSize: 12 }}>
                      <span style={{ width: 160 }}>公司</span>
                      <span style={{ width: 140 }}>职位</span>
                      <span style={{ width: 140 }}>时段</span>
                      <span style={{ flex: 1 }}>详情</span>
                      <span style={{ width: 40 }} />
                    </div>
                  )}
                  {fields.map((field) => (
                    <div key={field.key} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "flex-start" }}>
                      <Form.Item name={[field.name, "company"]} noStyle>
                        <Input placeholder="公司" style={{ width: 160 }} />
                      </Form.Item>
                      <Form.Item name={[field.name, "title"]} noStyle>
                        <Input placeholder="职位" style={{ width: 140 }} />
                      </Form.Item>
                      <Form.Item name={[field.name, "period"]} noStyle>
                        <Input placeholder="如 2018.03-至今" style={{ width: 140 }} />
                      </Form.Item>
                      <div style={{ flex: 1 }}>
                        <Form.Item name={[field.name, "description"]} noStyle>
                          <Input.TextArea autoSize placeholder="工作详情" style={{ width: "100%" }} />
                        </Form.Item>
                      </div>
                      <Button type="text" danger size="small" style={{ width: 40 }} onClick={() => remove(field.name)}>
                        删除
                      </Button>
                    </div>
                  ))}
                  <Button type="dashed" size="small" block onClick={() => add()}>
                    ＋ 添加工作经历
                  </Button>
                </div>
              )}
            </Form.List>
          </Form.Item>
          <Form.Item label="科研成果" style={{ marginBottom: 12 }}>
            <Form.List name="achievements_list">
              {(fields, { add, remove }) => (
                <div style={{ border: "1px solid #f0f0f0", borderRadius: 8, padding: 8 }}>
                  {fields.length > 0 && (
                    <div style={{ display: "flex", gap: 8, marginBottom: 4, color: "#888", fontSize: 12 }}>
                      <span style={{ width: 120 }}>类型</span>
                      <span style={{ flex: 1 }}>详情</span>
                      <span style={{ width: 40 }} />
                    </div>
                  )}
                  {fields.map((field) => (
                    <div key={field.key} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "flex-start" }}>
                      <Form.Item name={[field.name, "type"]} noStyle>
                        <Select options={ACH_TYPE_OPTIONS} style={{ width: 120 }} />
                      </Form.Item>
                      <div style={{ flex: 1 }}>
                        <Form.Item name={[field.name, "detail"]} noStyle>
                          <Input.TextArea autoSize placeholder="成果详情（标题 / 期刊 / 编号 / 时间等）" style={{ width: "100%" }} />
                        </Form.Item>
                      </div>
                      <Button type="text" danger size="small" style={{ width: 40 }} onClick={() => remove(field.name)}>
                        删除
                      </Button>
                    </div>
                  ))}
                  <Button type="dashed" size="small" block onClick={() => add({ type: "papers" })}>
                    ＋ 添加科研成果
                  </Button>
                </div>
              )}
            </Form.List>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

function ResumeDetail({ resume }: { resume: Resume }) {
  const s = resume.structured || {};
  const exps: any[] = Array.isArray(s.work_experiences) ? s.work_experiences : [];
  const ach: Record<string, any> = s.achievements && typeof s.achievements === "object" ? s.achievements : {};
  const intention: Record<string, any> =
    s.intention_detail && typeof s.intention_detail === "object" ? s.intention_detail : {};
  const hasIntentionDetail = Object.keys(INTENTION_LABELS).some((k) => intention[k]);
  const err = parseError(resume);
  return (
    <div style={{ padding: "4px 8px" }}>
      {err && <Typography.Text type="danger">解析错误：{err}</Typography.Text>}
      <Typography.Paragraph style={{ marginBottom: 8 }}>
        <b>履历摘要：</b>{s.work_history || "-"}
        {(s.phone || s.email) && (
          <span style={{ marginLeft: 16 }}><b>联系方式：</b>{[s.phone, s.email].filter(Boolean).join(" / ")}</span>
        )}
      </Typography.Paragraph>

      <b>个人意愿：</b>
      {hasIntentionDetail ? (
        <ul style={{ margin: "4px 0 8px", paddingLeft: 20 }}>
          {Object.entries(INTENTION_LABELS).map(([k, label]) =>
            intention[k] ? (
              <li key={k}>
                <b>{label}：</b>{intention[k]}
              </li>
            ) : null
          )}
        </ul>
      ) : (
        <span style={{ marginLeft: 8 }}>{s.intention || "未提取到"}</span>
      )}

      <div style={{ marginTop: 8 }}>
        <b>工作经历：</b>
        {exps.length ? (
          <ul style={{ margin: "4px 0", paddingLeft: 20 }}>
            {exps.map((e: any, i: number) => (
              <li key={i} style={{ marginBottom: 4 }}>
                <b>{e.company || "-"}</b> · {e.title || "-"}
                <span style={{ color: "#999", marginLeft: 8 }}>{e.period || ""}</span>
                {e.description && <div style={{ color: "#555" }}>{e.description}</div>}
              </li>
            ))}
          </ul>
        ) : (
          <span style={{ color: "#999", marginLeft: 8 }}>未提取到</span>
        )}
      </div>

      <div style={{ marginTop: 8 }}>
        <b>科研成果：</b>
        {Object.keys(ACH_LABELS).some((k) => (ach[k] || []).length) ? (
          Object.entries(ACH_LABELS).map(([k, label]) =>
            (ach[k] || []).length ? (
              <div key={k} style={{ marginTop: 4 }}>
                <Tag>{label}</Tag>
                <ul style={{ margin: "4px 0", paddingLeft: 20, display: "inline-block", verticalAlign: "top" }}>
                  {(ach[k] as string[]).map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null
          )
        ) : (
          <span style={{ color: "#999", marginLeft: 8 }}>未提取到</span>
        )}
      </div>
    </div>
  );
}

function AlertBanner({ resume }: { resume?: Resume }) {
  if (!resume) return null;
  const low = Object.entries(resume.confidence || {}).filter(([k, v]) => typeof v === "number" && v < 0.7);
  if (!low.length) return null;
  return (
    <div style={{ marginBottom: 12, color: "#faad14" }}>
      以下字段 AI 置信度较低，请核对原件后修正：{low.map(([k]) => FIELD_LABELS[k] || k).join("、")}
    </div>
  );
}
