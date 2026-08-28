import axios from "axios";

export const api = axios.create({ baseURL: "/api", timeout: 300000 });

// ---------- 类型 ----------
export interface Resume {
  id: number;
  name: string;
  structured: Record<string, any>;
  confidence: Record<string, any>;
  status: string;
  source: string;
  created_at: string;
}

export interface Job {
  id: number;
  title: string;
  department: string;
  raw_text: string;
  hard_conditions: Record<string, any>;
  soft_conditions: Record<string, any>;
  status: string;
  created_at: string;
}

export interface MatchRecord {
  id: number;
  job_id: number;
  resume_id: number;
  resume_name: string;
  vector_score: number;
  score: number;
  reason: string;
  push_status: string;
  created_at: string;
}

// ---------- 状态标签 ----------
export const STATUS_MAP: Record<string, { label: string; color: string }> = {
  in_pool: { label: "在库", color: "blue" },
  pushed: { label: "已推送", color: "orange" },
  selected: { label: "被选中", color: "green" },
  rejected: { label: "未选中", color: "default" },
  withdrawn: { label: "已退出", color: "red" },
};

/** 展示用姓名：一律优先取解析/修正后的 structured.name，仅在其为空时回退到 resume.name（文件名兜底） */
export const displayName = (r: Pick<Resume, "name" | "structured">) => r.structured?.name || r.name;

// ---------- API ----------
export const resumeApi = {
  /** 单文件上传：逐文件请求，成功/失败可精确对应到具体文件 */
  upload: (file: File, source: string) => {
    const fd = new FormData();
    fd.append("files", file);
    return api.post<Resume[]>(`/resumes/upload?source=${encodeURIComponent(source)}`, fd);
  },
  list: (params: { keyword?: string; status?: string; low_confidence_only?: boolean; limit?: number }) =>
    api.get<Resume[]>("/resumes", { params }),
  update: (id: number, body: Partial<Pick<Resume, "structured" | "status" | "source">>) =>
    api.patch<Resume>(`/resumes/${id}`, body),
  raw: (id: number) => api.get<{ raw_text: string }>(`/resumes/${id}/raw`),
  reparse: (id: number) => api.post<Resume>(`/resumes/${id}/reparse`),
  remove: (id: number) => api.delete(`/resumes/${id}`),
};

export const jobApi = {
  create: (body: { title: string; department: string; raw_text: string }) =>
    api.post<Job>("/jobs", body),
  list: () => api.get<Job[]>("/jobs"),
  remove: (id: number) => api.delete(`/jobs/${id}`),
};

export const matchApi = {
  run: (jobId: number) =>
    api.post<{ total_after_hard_filter: number; candidates: MatchRecord[] }>(`/match/run/${jobId}`),
  list: (jobId: number) => api.get<MatchRecord[]>(`/match/${jobId}`),
  push: (matchIds: number[]) => api.post("/match/push", { match_ids: matchIds }),
  feedback: (matchId: number, result: "selected" | "rejected") =>
    api.post("/match/feedback", { match_id: matchId, result }),
  exportUrl: (jobId: number) => `/api/match/${jobId}/export`,
};
