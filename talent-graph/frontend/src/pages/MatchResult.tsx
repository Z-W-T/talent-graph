import { Button, Card, Drawer, Modal, Progress, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { displayName, jobApi, matchApi, resumeApi, type Job, type MatchRecord } from "../api/client";

export default function MatchResultPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState<number>();
  const [matches, setMatches] = useState<MatchRecord[]>([]);
  const [running, setRunning] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([]);
  const [rawText, setRawText] = useState<string>();
  const [reasonDetail, setReasonDetail] = useState<MatchRecord>();
  /** resume_id -> 解析姓名：匹配记录里的 resume_name 是库字段快照（可能是文件名），姓名展示统一以 structured.name 为准 */
  const [nameMap, setNameMap] = useState<Record<number, string>>({});

  const loadNames = () =>
    resumeApi.list({ limit: 500 }).then((r) =>
      setNameMap(Object.fromEntries(r.data.map((x) => [x.id, displayName(x)])))
    );
  const nameOf = (m: MatchRecord) => nameMap[m.resume_id] || m.resume_name;

  useEffect(() => {
    jobApi.list().then((r) => setJobs(r.data));
    loadNames();
  }, []);

  const refresh = (id: number) => matchApi.list(id).then((r) => setMatches(r.data));

  const run = async () => {
    if (!jobId) return message.warning("请先选择岗位");
    setRunning(true);
    try {
      const r = await matchApi.run(jobId);
      setMatches(r.data.candidates);
      loadNames(); // 匹配前可能刚修正过姓名，同步最新映射
      message.success(`硬性过滤通过 ${r.data.total_after_hard_filter} 份，输出 Top ${r.data.candidates.length} 候选`);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "匹配执行失败");
    } finally {
      setRunning(false);
    }
  };

  const push = async () => {
    if (selectedRowKeys.length === 0) return message.warning("请先勾选要推送的候选人");
    await matchApi.push(selectedRowKeys);
    message.success(`已推送 ${selectedRowKeys.length} 人，简历状态更新为「已推送」`);
    setSelectedRowKeys([]);
    if (jobId) refresh(jobId);
  };

  const columns = [
    { title: "姓名", width: 100, render: (_: unknown, r: MatchRecord) => nameOf(r) },
    {
      title: "综合分",
      dataIndex: "score",
      width: 130,
      sorter: (a: MatchRecord, b: MatchRecord) => a.score - b.score,
      render: (v: number) => <Progress percent={v} size="small" status={v >= 80 ? "success" : "normal"} />,
    },
    { title: "向量相似度", dataIndex: "vector_score", width: 100, render: (v: number) => v.toFixed(3) },
    {
      title: "匹配理由（可追溯）",
      dataIndex: "reason",
      ellipsis: true,
      render: (v: string, r: MatchRecord) => <a onClick={() => setReasonDetail(r)}>{v || "（无）"}</a>,
    },
    {
      title: "推送状态",
      dataIndex: "push_status",
      width: 100,
      render: (v: string) => {
        const map: Record<string, [string, string]> = {
          pending: ["待推送", "default"], pushed: ["已推送", "orange"],
          selected: ["有意向", "green"], rejected: ["无意向", "red"],
        };
        const [label, color] = map[v] || [v, "default"];
        return <Tag color={color}>{label}</Tag>;
      },
    },
    {
      title: "反馈（模拟单位回填）",
      width: 170,
      render: (_: unknown, r: MatchRecord) =>
        r.push_status === "pushed" ? (
          <Space>
            <a onClick={() => matchApi.feedback(r.id, "selected").then(() => { if (jobId) refresh(jobId); })}>有意向</a>
            <a onClick={() => matchApi.feedback(r.id, "rejected").then(() => { if (jobId) refresh(jobId); })}>无意向</a>
          </Space>
        ) : null,
    },
  ];

  return (
    <Card title="两级匹配：硬性过滤 → 向量粗排 → LLM 精排（逐条理由）">
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          style={{ width: 280 }}
          placeholder="选择岗位"
          value={jobId}
          onChange={(v) => {
            setJobId(v);
            refresh(v);
          }}
          options={jobs.map((j) => ({ value: j.id, label: `${j.title}（${j.department || "未填部门"}）` }))}
        />
        <Button type="primary" onClick={run} loading={running}>
          执行匹配
        </Button>
        <Button onClick={push} disabled={selectedRowKeys.length === 0}>
          推送精选（{selectedRowKeys.length}）
        </Button>
        {jobId && (
          <Button href={matchApi.exportUrl(jobId)} target="_blank">
            导出 Excel 名单
          </Button>
        )}
      </Space>

      <Table
        rowKey="id"
        size="small"
        columns={columns}
        dataSource={matches}
        pagination={false}
        rowSelection={{ selectedRowKeys, onChange: (keys) => setSelectedRowKeys(keys as number[]) }}
      />

      <Modal open={!!reasonDetail} footer={null} onCancel={() => setReasonDetail(undefined)}
        title={`匹配理由 · ${reasonDetail ? nameOf(reasonDetail) : ""}`} width={640}>
        <Typography.Paragraph>{reasonDetail?.reason}</Typography.Paragraph>
        <a onClick={() => reasonDetail && resumeApi.raw(reasonDetail.resume_id).then((r) => setRawText(r.data.raw_text))}>
          查看简历原文（溯源）
        </a>
      </Modal>

      <Drawer open={rawText !== undefined} onClose={() => setRawText(undefined)} title="简历解析原文" width={560}>
        <pre style={{ whiteSpace: "pre-wrap" }}>{rawText}</pre>
      </Drawer>
    </Card>
  );
}
