"""组织架构：多层级需求部门的层级数据源。

- 层级树持久化在数据库 departments 表（邻接表：id/name/parent_id/province/sort）。
- 前端经 GET /api/departments 加载树，用于岗位需求「需求部门」的级联（Cascader）选择。
- 节点自带 province（所在省份），子节点留空则继承最近有省份的祖先；岗位的省份由
  所选部门路径推导（`resolve_province`），因此前端不需要再单独选择省份。
- 支持 Excel 批量导入（每行 = 一个节点的完整路径 + 可选省份）与「恢复默认示例」。
- 下方 DEPARTMENT_TREE 仅为内置示例树，用于：首次建库播种 / 一键恢复默认；
  正式数据以 Excel 导入或数据库中的维护为准。
- 节点约定：label 与 value 相同（均为部门中文名）；path = ["集团总部", "人力资源部", ...]。
"""

from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Department

DEPARTMENT_TREE: list[dict] = [
    {
        "value": "集团总部",
        "label": "集团总部",
        "province": "北京",
        "children": [
            {"value": "发展策划部", "label": "发展策划部",
             "children": [
                 {"value": "规划处", "label": "规划处"},
                 {"value": "项目处", "label": "项目处"},
                 {"value": "新能源处", "label": "新能源处"},
             ]},
            {"value": "人力资源部", "label": "人力资源部",
             "children": [
                 {"value": "人才引进处", "label": "人才引进处"},
                 {"value": "培训处", "label": "培训处"},
                 {"value": "薪酬绩效处", "label": "薪酬绩效处"},
             ]},
            {"value": "调度控制中心", "label": "调度控制中心",
             "children": [
                 {"value": "调度运行处", "label": "调度运行处"},
                 {"value": "运行方式处", "label": "运行方式处"},
                 {"value": "调度自动化处", "label": "调度自动化处"},
                 {"value": "继电保护处", "label": "继电保护处"},
             ]},
            {"value": "科技创新与数字化部", "label": "科技创新与数字化部"},
            {"value": "安全监察质量部", "label": "安全监察质量部"},
            {"value": "财务资产部", "label": "财务资产部"},
            {"value": "物资部", "label": "物资部"},
            {"value": "党建工作部", "label": "党建工作部"},
        ],
    },
    {
        "value": "省级电力公司",
        "label": "省级电力公司（示例）",
        "province": "广东",
        "children": [
            {"value": "调度中心", "label": "调度中心"},
            {"value": "设备管理部", "label": "设备管理部"},
            {"value": "人力资源部", "label": "人力资源部"},
            {"value": "电力营销部", "label": "电力营销部"},
            {"value": "电网建设部", "label": "电网建设部"},
            {"value": "财务资产部", "label": "财务资产部"},
        ],
    },
    {
        "value": "科研院所与设计单位",
        "label": "科研院所与设计单位（示例）",
        "province": "北京",
        "children": [
            {"value": "电力科学研究院", "label": "电力科学研究院",
             "children": [
                 {"value": "新能源并网研究所", "label": "新能源并网研究所"},
                 {"value": "储能技术研究所", "label": "储能技术研究所"},
                 {"value": "电网仿真研究所", "label": "电网仿真研究所"},
             ]},
            {"value": "电力设计院", "label": "电力设计院"},
            {"value": "经济技术研究院", "label": "经济技术研究院"},
        ],
    },
    {
        "value": "产业与新兴业务公司",
        "label": "产业与新兴业务公司（示例）",
        "province": "江苏",
        "children": [
            {"value": "综合能源服务公司", "label": "综合能源服务公司"},
            {"value": "电动汽车服务公司", "label": "电动汽车服务公司"},
            {"value": "储能事业部", "label": "储能事业部"},
            {"value": "信息通信分公司", "label": "信息通信分公司"},
        ],
    },
]


def path_to_department(path: list[str]) -> str:
    """级联路径 -> 展示用字符串（以 / 分隔）。"""
    return "/".join(str(x).strip("/") for x in path if str(x).strip("/"))


def department_to_path(department: str) -> list[str]:
    """兼容旧数据/Excel 导入：把 "集团总部/人力资源部" 之类的字符串拆成路径。"""
    return [seg.strip() for seg in (department or "").split("/") if seg.strip()]


# ---------- 数据库读写（departments 表为唯一数据源） ----------

def node_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Department)) or 0


def ensure_path(db: Session, parts: Sequence[str], province: str = "") -> Department | None:
    """按「从根到本级」的路径逐级查找/创建部门节点，返回最深层节点。

    幂等：节点已存在则直接复用，不会重复建；同级按 sort 递增追加顺序。
    province 只作用于路径最深的一个节点（若该节点已有省份就不覆盖），
    中间层级留空即可，由子节点继承。
    """
    names = [str(p).strip() for p in parts if str(p).strip()]
    last: Department | None = None
    parent_id: int | None = None
    for pos, name in enumerate(names):
        stmt = select(Department).where(Department.name == name)
        stmt = (stmt.where(Department.parent_id.is_(None)) if parent_id is None
                else stmt.where(Department.parent_id == parent_id))
        node = db.scalar(stmt)
        if node is None:
            max_stmt = select(func.max(Department.sort))
            max_stmt = (max_stmt.where(Department.parent_id.is_(None)) if parent_id is None
                        else max_stmt.where(Department.parent_id == parent_id))
            max_sort = db.scalar(max_stmt) or 0
            node = Department(name=name, parent_id=parent_id, sort=int(max_sort) + 1)
            db.add(node)
            db.flush()  # 先拿到自增 id 供下级挂接
        if province and pos == len(names) - 1 and not node.province:
            node.province = province      # 仅补齐空值，不覆盖人工维护的省份
        last = node
        parent_id = node.id
    return last


def find_node(db: Session, parts: Sequence[str]) -> Department | None:
    """按「从根到本级」路径精确查找部门节点（逐级比较名称+父级）。"""
    parent_id: int | None = None
    node: Department | None = None
    for raw in parts:
        name = str(raw).strip()
        if not name:
            return None
        stmt = select(Department).where(Department.name == name)
        stmt = (stmt.where(Department.parent_id.is_(None)) if parent_id is None
                else stmt.where(Department.parent_id == parent_id))
        node = db.scalar(stmt)
        if node is None:
            return None
        parent_id = node.id
    return node


def resolve_province(db: Session, parts: Sequence[str]) -> str:
    """部门路径 -> 岗位所在省份：取路径上最深的、有省份的节点。

    节点省份留空即表示「跟随上级」，因此子部门无需重复录入省份。
    路径在组织架构中不存在时按已能匹配到的前缀回答（找不到则返回空串）。
    """
    parent_id: int | None = None
    province = ""
    for raw in parts:
        name = str(raw).strip()
        if not name:
            continue
        stmt = select(Department).where(Department.name == name)
        stmt = (stmt.where(Department.parent_id.is_(None)) if parent_id is None
                else stmt.where(Department.parent_id == parent_id))
        node = db.scalar(stmt)
        if node is None:
            break
        if node.province:
            province = node.province
        parent_id = node.id
    return province


def backfill_default_provinces(db: Session) -> int:
    """旧库升级：给已存在的内置示例部门补上省份（只补空值，不覆盖人工维护的省份）。

    新加的 departments.province 列在旧 .db 里默认为空，若不补齐，老库升级后所有岗位
    都会带不出省份。这里按内置示例树的路径匹配同名节点补值。
    """
    updated = 0
    for path, province in _flatten_tree(DEPARTMENT_TREE):
        if not province:
            continue
        node = find_node(db, path)
        if node is not None and not node.province:
            node.province = province
            updated += 1
    if updated:
        db.commit()
    return updated


def set_province(db: Session, node_id: int, province: str) -> Department:
    """设置某个部门节点的所在省份（留空则恢复为继承上级）。"""
    node = db.get(Department, node_id)
    if node is None:
        raise ValueError("部门节点不存在")
    node.province = (province or "").strip()
    db.commit()
    return node


def load_tree(db: Session) -> list[dict]:
    """读取 departments 表并组装成前端级联/树形结构（根 -> 子）。

    province 为该节点自身的省份（可能为空 = 继承上级），同时附上 effect_province
    便于直接展示，无需前端再递归推导。
    """
    rows = list(db.scalars(select(Department).order_by(Department.sort, Department.id)))
    children_map: dict[int | None, list[Department]] = {}
    for r in rows:
        children_map.setdefault(r.parent_id, []).append(r)

    def build(parent_id: int | None, inherited: str = "") -> list[dict]:
        out: list[dict] = []
        for n in children_map.get(parent_id, []):
            eff = n.province or inherited
            node = {"id": n.id, "value": n.name, "label": n.name,
                    "province": n.province or "", "effect_province": eff}
            subs = build(n.id, eff)
            if subs:
                node["children"] = subs
            out.append(node)
        return out

    return build(None)


def _flatten_tree(nodes: list[dict], prefix: tuple[str, ...] = ()) -> list[tuple[list[str], str]]:
    """把示例树常量压平成「从根到本级」的路径 + 该节点自身省份（留空 = 继承上级）。"""
    out: list[tuple[list[str], str]] = []
    for nd in nodes:
        path = [*prefix, nd["value"]]
        out.append((path, nd.get("province") or ""))
        out.extend(_flatten_tree(nd.get("children") or [], tuple(path)))
    return out


def seed_default(db: Session) -> None:
    """用内置示例树（DEPARTMENT_TREE）重建全部部门节点并提交。"""
    for path, province in _flatten_tree(DEPARTMENT_TREE):
        ensure_path(db, path, province)
    db.commit()


def ensure_default_seeded(db: Session) -> None:
    """启动兜底：表为空时播种默认示例树，避免级联/岗位录入无任何可选部门。"""
    if node_count(db) == 0:
        seed_default(db)


def clear_all(db: Session) -> None:
    """清空全部部门（父级 delete 触发 delete-orphan 级联删子级）。"""
    roots = list(db.scalars(select(Department).where(Department.parent_id.is_(None))))
    for root in roots:
        db.delete(root)
    db.flush()


def reset_to_default(db: Session) -> None:
    """清空后恢复内置默认示例树。"""
    clear_all(db)
    seed_default(db)


def delete_node(db: Session, node_id: int) -> None:
    """删除部门节点；存在下级部门时拒绝（避免产生悬空层级）。"""
    node = db.get(Department, node_id)
    if node is None:
        raise ValueError("部门节点不存在")
    if node.children:
        raise ValueError(f"「{node.name}」存在下级部门，请先删除其下级")
    db.delete(node)
    db.commit()


def import_paths(db: Session, rows: list[dict]) -> dict:
    """按「部门全路径（+ 可选省份）」批量导入（逐行 upsert、逐行容错）。

    rows: [{row: Excel行号, path: "集团总部/人力资源部", province: "北京"（可空）}, ...]
    返回: {total, succeeded, failed, errors:[{row, message}]}
    """
    result = {"total": len(rows), "succeeded": 0, "failed": 0, "errors": []}
    for item in rows:
        row_no = item.get("row")
        try:
            path = department_to_path(item.get("path") or "")
            if not path:
                raise ValueError("路径为空")
            ensure_path(db, path, str(item.get("province") or "").strip())
            db.commit()  # 每行提交：单行失败回滚不影响已成功的行
            result["succeeded"] += 1
        except Exception as e:
            db.rollback()
            result["failed"] += 1
            result["errors"].append({"row": row_no, "message": str(e)[:200]})
    return result
