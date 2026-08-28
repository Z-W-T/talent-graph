import { Button, Card, Descriptions, Form, Input, List, Popconfirm, Space, Tag, message } from "antd";
import { useEffect, useState } from "react";
import { jobApi, type Job } from "../api/client";

const EXAMPLE = `例：我们需要一位电力系统自动化方向的博士，35 岁以下，研究方向偏新能源并网或储能调度，
熟悉 PSCAD/MATLAB 仿真，有电网调度或设计院经验优先，能到深圳全职工作。`;

export default function JobRequestPage() {
  const [form] = Form.useForm();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const refresh = () => jobApi.list().then((r) => setJobs(r.data));
  useEffect(() => {
    refresh();
  }, []);

  const onFinish = async (values: { title: string; department: string; raw_text: string }) => {
    setSubmitting(true);
    try {
      await jobApi.create(values);
      message.success("岗位需求已结构化并入库");
      form.resetFields();
      refresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "提交失败，请检查内部大模型平台连接");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card title="岗位需求录入（自然语言描述，AI 自动结构化为硬性 + 择优条件）">
        <Form form={form} layout="vertical" onFinish={onFinish}>
          <Form.Item name="title" label="岗位名称" rules={[{ required: true, message: "请填写岗位名称" }]}>
            <Input placeholder="如：新能源并网高级工程师" />
          </Form.Item>
          <Form.Item name="department" label="需求部门">
            <Input placeholder="如：调度中心" />
          </Form.Item>
          <Form.Item name="raw_text" label="需求描述（把和业务部门对话访谈的内容粘贴在这里）"
            rules={[{ required: true, message: "请填写需求描述" }]}>
            <Input.TextArea rows={5} placeholder={EXAMPLE} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting}>
            结构化并入库
          </Button>
        </Form>
      </Card>

      <Card title="已录入岗位">
        <List
          dataSource={jobs}
          renderItem={(job) => (
            <List.Item
              actions={[
                <Popconfirm key="del" title="删除该岗位及其匹配记录？" onConfirm={() => jobApi.remove(job.id).then(refresh)}>
                  <a>删除</a>
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space>
                    {job.title}
                    <Tag>{job.department || "未填部门"}</Tag>
                  </Space>
                }
                description={
                  <Descriptions size="small" column={1} style={{ marginTop: 8 }}>
                    <Descriptions.Item label="硬性条件">
                      {JSON.stringify(job.hard_conditions)}
                    </Descriptions.Item>
                    <Descriptions.Item label="择优条件">
                      {JSON.stringify(job.soft_conditions)}
                    </Descriptions.Item>
                  </Descriptions>
                }
              />
            </List.Item>
          )}
        />
      </Card>
    </Space>
  );
}
