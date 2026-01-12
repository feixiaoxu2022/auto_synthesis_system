#!/usr/bin/env python3
"""
基于队列优化的统一任务分配规则算法实现
用于验证样本的唯一性和自动筛选合格样本
"""

import json
import random
import heapq
from typing import List, Dict, Any, Tuple, Optional, Set
from datetime import datetime, timedelta
import copy

class QueueBasedAssignmentAlgorithm:
    """基于队列的任务分配算法 - 优化依赖关系处理"""
    
    def __init__(self):
        # 核心队列
        self.ready_queue = []               # 优先队列：已就绪任务 [(priority, task)]
        self.waiting_queue = {}             # 等待队列：{task_id: task}
        self.completed_set = set()          # 已完成任务集合
        
        # 高效查找映射
        self.task_map = {}                  # {task_id: task}
        self.worker_map = {}                # {worker_id: worker}
        self.dependencies = {}              # {task_id: [dep_task_ids]}
        self.dependents = {}                # {task_id: [dependent_task_ids]}
        
        # 经验等级描述
        self.experience_desc = {
            "junior": "初级",
            "intermediate": "中级", 
            "senior": "高级"
        }
    
    def calculate_priority(self, task: Dict[str, Any]) -> Tuple[int, int]:
        """
        简化的优先级计算 - 确保Agent可完全预测任务处理顺序
        
        基于统一配置文件中的task_processing_order规则：
        1. 按urgency_level降序排列 (10 > 9 > 8 > ... > 1)
        2. urgency_level相同时，按complexity_score降序排列 (10 > 9 > 8 > ... > 1)
        
        返回tuple用于排序，值越大优先级越高
        """
        urgency = task.get('urgency_level', 0)
        complexity = task.get('complexity_score', 0)
        
        # 返回(urgency, complexity)元组，heapq会按此排序
        return (urgency, complexity)
    
    def _build_dependency_graphs(self, tasks: List[Dict[str, Any]]):
        """构建正向和反向依赖图 - 清理无效依赖"""
        self.dependencies.clear()
        self.dependents.clear()
        
        # 先清理任务的无效依赖
        for task in tasks:
            task_id = task['task_id']
            original_deps = task.get('dependencies') or []
            
            # 只保留存在于当前任务集合中的依赖
            valid_deps = [dep for dep in original_deps if dep in self.task_map]
            
            # 更新任务对象，移除无效依赖
            if len(valid_deps) != len(original_deps):
                print(f"清理任务 {task_id} 的无效依赖: {set(original_deps) - set(valid_deps)}")
                task['dependencies'] = valid_deps if valid_deps else None
            
            self.dependencies[task_id] = valid_deps
            
            # 构建反向依赖图
            for dep_id in valid_deps:
                if dep_id not in self.dependents:
                    self.dependents[dep_id] = []
                self.dependents[dep_id].append(task_id)
    
    def _all_dependencies_satisfied(self, task_id: str) -> bool:
        """检查任务的所有依赖是否已满足 - O(k)时间复杂度"""
        for dep_id in self.dependencies.get(task_id, []):
            if dep_id not in self.completed_set:
                return False
        return True
    
    def _initialize_queues(self, tasks: List[Dict[str, Any]]):
        """智能初始化队列"""
        self.ready_queue.clear()
        self.waiting_queue.clear()
        self.completed_set.clear()
        
        for task in tasks:
            if task.get('status') != 'pending':
                continue
                
            task_id = task['task_id']
            
            if not self.dependencies.get(task_id):
                # 无依赖任务直接进入就绪队列
                priority_tuple = self.calculate_priority(task)
                # 使用负值实现最大堆：(-urgency, -complexity, task_id)
                heapq.heappush(self.ready_queue, (-priority_tuple[0], -priority_tuple[1], task_id))
            else:
                # 有依赖任务进入等待队列
                self.waiting_queue[task_id] = task
    
    def _activate_dependent_tasks(self, completed_task_id: str):
        """任务完成后，激活等待中的依赖任务"""
        for dependent_id in self.dependents.get(completed_task_id, []):
            if dependent_id in self.waiting_queue:
                # 检查该依赖任务的所有依赖是否都满足
                if self._all_dependencies_satisfied(dependent_id):
                    task = self.waiting_queue.pop(dependent_id)
                    priority_tuple = self.calculate_priority(task)
                    # 使用负值实现最大堆：(-urgency, -complexity, task_id)
                    heapq.heappush(self.ready_queue, (-priority_tuple[0], -priority_tuple[1], dependent_id))
    
    def assign_task(self, task: Dict[str, Any], workers: List[Dict[str, Any]], all_tasks: List[Dict[str, Any]] = None) -> Tuple[bool, Optional[Dict], str]:
        """
        为单个任务分配最合适的人员 - 保持向后兼容性
        """
        # 检查任务状态
        if task.get("status") != "pending":
            return False, None, f"任务状态为{task.get('status')}，不是pending"
        
        # 基本要求筛选
        candidates = self._filter_basic_requirements(task, workers)
        if not candidates:
            return False, None, "没有满足基本要求的候选人员（可用且技能匹配）"
        
        # 根据任务特性选择最优人员
        best_worker, rationale = self._select_best_worker(task, candidates)
        
        if not best_worker:
            return False, None, "无法确定最优人员"
        
        # 构造分配结果
        assignment_result = {
            "worker_id": best_worker["worker_id"],
            "rationale": rationale,
            "task_id": task["task_id"]
        }
        
        return True, assignment_result, f"成功分配给 {best_worker['worker_id']}: {rationale}"
    
    def _filter_basic_requirements(self, task: Dict[str, Any], workers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """基本要求筛选：可用性 + 技能完全匹配"""
        candidates = []
        required_capabilities = set(task.get("required_capabilities", []))
        
        for worker in workers:
            # 检查可用性
            if worker.get("availability_status") != "available":
                continue
            
            # 检查技能完全覆盖：worker必须具备任务所需的全部技能
            worker_capabilities = set(worker.get("capabilities", []))
            if not required_capabilities.issubset(worker_capabilities):
                continue
            
            candidates.append(worker)
        
        return candidates
    
    def _select_best_worker(self, task: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Tuple[Optional[Dict], str]:
        """根据任务特性选择最优人员"""
        if not candidates:
            return None, "无候选人员"
        
        urgency_level = task.get("urgency_level", 0)
        complexity_score = task.get("complexity_score", 0)
        
        # 判断任务特性（简化逻辑：只基于urgency_level和complexity_score）
        is_urgent = urgency_level >= 8
        is_complex = complexity_score >= 7
        
        if is_urgent and is_complex:
            # 既紧急又复杂：优先经验，经验相同选负载低的
            return self._select_by_experience(candidates, "紧急复杂任务优先经验丰富人员")
        elif is_urgent:
            # 紧急任务：优先负载最低，负载相同选经验高的
            return self._select_by_lowest_workload_then_experience(candidates, "紧急任务优先快速响应")
        elif is_complex:
            # 复杂任务：优先选择senior级别人员
            return self._select_by_senior_experience(candidates, "复杂任务需要资深人员")
        else:
            # 常规任务：选择负载最低的人员
            return self._select_by_lowest_workload(candidates, "常规任务优先负载最低人员")
    
    def _select_by_experience(self, candidates: List[Dict[str, Any]], rationale_base: str) -> Tuple[Optional[Dict], str]:
        """按经验等级选择（优先高经验，同等经验选择负载最低）"""
        # 按经验等级分组
        candidates_by_exp = {"senior": [], "intermediate": [], "junior": []}
        
        for candidate in candidates:
            exp = candidate.get("experience_level", "junior")
            if exp in candidates_by_exp:
                candidates_by_exp[exp].append(candidate)
        
        # 选择最高经验等级
        for exp_level in ["senior", "intermediate", "junior"]:
            if candidates_by_exp[exp_level]:
                group = candidates_by_exp[exp_level]
                if len(group) == 1:
                    return group[0], f"{rationale_base} - 选择{exp_level}级别人员"
                else:
                    # 同等经验选择负载最低
                    best = min(group, key=lambda w: w.get("current_workload_hours", 0))
                    return best, f"{rationale_base} - {exp_level}级别中负载最低"
        
        return None, "无合适候选人"
    
    def _select_by_senior_experience(self, candidates: List[Dict[str, Any]], rationale_base: str) -> Tuple[Optional[Dict], str]:
        """选择senior级别人员（如果有多个则选择负载较低的）"""
        senior_candidates = [c for c in candidates if c.get("experience_level") == "senior"]
        
        if not senior_candidates:
            return None, "无senior级别人员可分配复杂任务"
        
        if len(senior_candidates) == 1:
            return senior_candidates[0], f"{rationale_base} - 唯一senior人员"
        else:
            # 多个senior选择负载较低的
            best = min(senior_candidates, key=lambda w: w.get("current_workload_hours", 0))
            return best, f"{rationale_base} - senior中负载较低"
    
    def _select_by_lowest_workload_then_experience(self, candidates: List[Dict[str, Any]], rationale_base: str) -> Tuple[Optional[Dict], str]:
        """按负载优先，负载相同时选择经验高的（紧急任务用）"""
        if len(candidates) == 1:
            return candidates[0], f"{rationale_base} - 唯一候选人"
        
        # 按负载排序
        sorted_candidates = sorted(candidates, key=lambda w: w.get("current_workload_hours", 0))
        
        # 找到负载最低的所有人员
        lowest_workload = sorted_candidates[0].get("current_workload_hours", 0)
        lowest_candidates = [c for c in sorted_candidates if c.get("current_workload_hours", 0) == lowest_workload]
        
        if len(lowest_candidates) == 1:
            return lowest_candidates[0], f"{rationale_base} - 负载最低({lowest_workload}h)"
        else:
            # 负载相同，选择经验最高的
            experience_order = {"senior": 3, "intermediate": 2, "junior": 1}
            best_exp_candidate = max(lowest_candidates, 
                                   key=lambda w: experience_order.get(w.get("experience_level", "junior"), 1))
            return best_exp_candidate, f"{rationale_base} - 负载最低且经验较高"
    
    def _select_by_lowest_workload(self, candidates: List[Dict[str, Any]], rationale_base: str) -> Tuple[Optional[Dict], str]:
        """选择负载最低的人员"""
        if len(candidates) == 1:
            return candidates[0], f"{rationale_base} - 唯一候选人"
        
        # 按负载排序
        sorted_candidates = sorted(candidates, key=lambda w: w.get("current_workload_hours", 0))
        
        # 检查是否有多个人负载相同（最低）
        lowest_workload = sorted_candidates[0].get("current_workload_hours", 0)
        lowest_candidates = [c for c in sorted_candidates if c.get("current_workload_hours", 0) == lowest_workload]
        
        if len(lowest_candidates) == 1:
            return lowest_candidates[0], f"{rationale_base} - 负载最低({lowest_workload}h)"
        else:
            return None, f"存在{len(lowest_candidates)}个人员负载相同({lowest_workload}h)，无法确定唯一最优"
    
    def validate_scenario_uniqueness(self, tasks: List[Dict[str, Any]], workers: List[Dict[str, Any]]) -> Tuple[bool, List[Dict], str]:
        """
        验证场景是否有唯一的分配方案 - 使用队列优化算法
        """
        # 创建副本避免修改原数据
        workers_copy = copy.deepcopy(workers)
        tasks_copy = copy.deepcopy(tasks)
        
        # 构建映射表
        self.task_map = {t['task_id']: t for t in tasks_copy}
        self.worker_map = {w['worker_id']: w for w in workers_copy}
        
        # 构建依赖关系图
        self._build_dependency_graphs(tasks_copy)
        
        # 检查依赖关系完整性
        missing_deps = []
        for task_id, deps in self.dependencies.items():
            for dep_id in deps:
                if dep_id not in self.task_map:
                    missing_deps.append(f"任务{task_id}依赖的{dep_id}不存在")
        
        if missing_deps:
            return False, [], f"依赖关系不完整: {'; '.join(missing_deps)}", None
        
        # 检查循环依赖
        if self._has_circular_dependency():
            return False, [], "存在循环依赖，无法分配", None
        
        # 初始化队列
        self._initialize_queues(tasks_copy)
        
        # 开始分配处理
        assignments = []
        processed_count = 0
        max_iterations = len(tasks_copy) * 2  # 防止无限循环
        
        print(f"开始队列处理，初始就绪任务: {len(self.ready_queue)}个，等待任务: {len(self.waiting_queue)}个")
        
        while self.ready_queue and processed_count < max_iterations:
            processed_count += 1
            
            # 取出最高优先级任务
            neg_urgency, neg_complexity, task_id = heapq.heappop(self.ready_queue)
            urgency = -neg_urgency
            complexity = -neg_complexity
            task = self.task_map[task_id]
            
            print(f"处理任务 {task_id} (紧急度: {urgency}, 复杂度: {complexity})")
            
            # 尝试分配
            success, assignment, reason = self.assign_task(task, workers_copy)
            
            if not success:
                print(f"任务{task_id}分配失败: {reason}")
                return False, [], f"任务{task_id}无法分配: {reason}", None
            
            if assignment:
                assignments.append(assignment)
                worker_id = assignment["worker_id"]
                
                # 找到分配的工作人员(使用当前状态)
                assigned_worker = next((w for w in workers_copy if w["worker_id"] == worker_id), None)
                if assigned_worker:
                    # 记录分配前的负载状态，用于生成准确的描述
                    pre_assignment_load = assigned_worker["current_workload_hours"]
                    
                    # 生成详细的分配描述信息
                    assignment["detailed_description"] = self._generate_assignment_description(
                        task, assigned_worker, assignment["rationale"], pre_assignment_load
                    )
                
                # 更新任务状态
                task["status"] = "assigned"
                task["assigned_worker_id"] = worker_id
                task["assignment_time"] = datetime.now().isoformat()
                task["assignment_rationale"] = assignment["rationale"]
                
                # 更新工作人员负载
                for worker in workers_copy:
                    if worker["worker_id"] == worker_id:
                        worker["current_workload_hours"] += task.get("required_hours", 0)
                        break
                
                # 标记任务完成并激活依赖任务
                self.completed_set.add(task_id)
                self._activate_dependent_tasks(task_id)
                
                print(f"任务{task_id}分配成功给{worker_id}，激活了{len(self.dependents.get(task_id, []))}个依赖任务")
        
        # 检查是否还有未处理的任务
        remaining_tasks = len(self.waiting_queue)
        if remaining_tasks > 0:
            return False, [], f"仍有{remaining_tasks}个任务无法分配（可能缺少满足条件的人员）", None
        
        # 验证所有pending任务都被分配
        pending_tasks = [t for t in tasks_copy if t.get("status") == "pending"]
        if pending_tasks:
            pending_ids = [t["task_id"] for t in pending_tasks]
            return False, [], f"以下任务未被分配: {pending_ids}", None
        
        print(f"队列处理完成！成功分配{len(assignments)}个任务，处理轮次: {processed_count}")
        return True, assignments, f"成功为{len(assignments)}个任务分配人员", workers_copy
    
    def _has_circular_dependency(self) -> bool:
        """检查是否存在循环依赖 - 使用DFS"""
        visited = set()
        rec_stack = set()
        
        def dfs(task_id: str) -> bool:
            if task_id in rec_stack:
                return True  # 发现循环
            
            if task_id in visited:
                return False  # 已访问过且无循环
            
            visited.add(task_id)
            rec_stack.add(task_id)
            
            # 访问所有依赖
            for dep_id in self.dependencies.get(task_id, []):
                if dfs(dep_id):
                    return True
            
            rec_stack.remove(task_id)
            return False
        
        # 检查所有任务
        for task_id in self.task_map.keys():
            if task_id not in visited:
                if dfs(task_id):
                    return True
        
        return False

    def _check_task_processing_order_uniqueness(self, tasks: List[Dict]) -> bool:
        """
        检查任务处理顺序是否唯一
        
        基于统一配置文件中的processing_order_uniqueness约束：
        所有任务的(urgency_level, complexity_score)组合必须唯一，确保在任何时刻
        队列中都不会出现优先级相同的任务，无论是否有依赖关系
        """
        priority_groups = {}
        
        for task in tasks:
            # 检查所有任务，无论是否有依赖关系
            priority_key = (
                task.get('urgency_level', 0),
                task.get('complexity_score', 0)
            )
            if priority_key not in priority_groups:
                priority_groups[priority_key] = []
            priority_groups[priority_key].append(task['task_id'])
        
        # 检查是否有相同优先级的任务组
        conflicting_groups = []
        for priority_key, task_ids in priority_groups.items():
            if len(task_ids) > 1:
                conflicting_groups.append({
                    'priority': priority_key,
                    'task_ids': task_ids
                })
        
        if conflicting_groups:
            print("❌ 任务处理顺序不唯一，发现以下冲突：")
            for group in conflicting_groups:
                urgency, complexity = group['priority']
                print(f"  优先级(紧急度={urgency}, 复杂度={complexity}): {group['task_ids']}")
            return False
        else:
            print("✅ 任务处理顺序唯一性检查通过")
            return True


    def _generate_assignment_description(self, task: Dict, worker: Dict, rationale: str, pre_load: float) -> Dict:
        """在分配时生成准确的描述信息"""
        required_caps = task["required_capabilities"]
        required_hours = task.get("required_hours", 0)
        urgency = task["urgency_level"]
        complexity = task["complexity_score"]
        
        # 任务描述
        task_type = "📋常规任务"
        if urgency >= 8:
            task_type = "🔥紧急任务"
        elif complexity >= 7:
            task_type = "🧠复杂任务"
        
        task_description = f"{task_type}(紧急度{urgency}/复杂度{complexity})，需要{required_caps}技能，预计{required_hours}小时"
        
        # 工作人员描述
        worker_exp = self.experience_desc.get(worker["experience_level"], worker["experience_level"])
        worker_caps = worker["capabilities"]
        worker_description = f"{worker['worker_id']}({worker_exp})，技能{worker_caps}，当前负载{pre_load}h"
        
        # 合理性分析
        reasoning_points = []
        
        # 技能匹配检查
        task_caps_set = set(required_caps)
        worker_caps_set = set(worker_caps)
        if task_caps_set.issubset(worker_caps_set):
            reasoning_points.append(f"✅ 技能完全匹配: {list(task_caps_set)}")
        else:
            missing_skills = task_caps_set - worker_caps_set
            reasoning_points.append(f"❌ 缺少技能: {list(missing_skills)}")
        
        # 可用性检查
        if worker["availability_status"] == "available":
            reasoning_points.append("✅ 人员可用")
        else:
            reasoning_points.append(f"❌ 人员状态: {worker['availability_status']}")
        
        # 优先级逻辑检查
        if urgency >= 8 and complexity >= 7:
            if worker["experience_level"] == "senior":
                reasoning_points.append("✅ 紧急复杂任务选择高级人员")
            else:
                reasoning_points.append(f"⚠️ 紧急复杂任务但选择了{worker_exp}人员")
        elif urgency >= 8:
            reasoning_points.append("✅ 紧急任务优先快速响应")
        elif complexity >= 7:
            if worker["experience_level"] == "senior":
                reasoning_points.append("✅ 复杂任务选择高级人员")
            else:
                reasoning_points.append(f"⚠️ 复杂任务但选择了{worker_exp}人员")
        else:
            reasoning_points.append("✅ 常规任务按负载优先原则")
        
        # 负载影响
        new_load = pre_load + required_hours
        reasoning_points.append(f"📊 负载变化: {pre_load}h → {new_load}h")
        
        return {
            "task_description": task_description,
            "worker_description": worker_description,
            "rationale": rationale,
            "reasoning_analysis": reasoning_points
        }


# 向后兼容性：保持原有的类名和接口
class UniversalAssignmentAlgorithm(QueueBasedAssignmentAlgorithm):
    """向后兼容的包装类"""
    pass


class ScenarioGenerator:
    """场景生成器 - 随机组装并筛选合格样本"""
    
    def __init__(self, workers_pool: List[Dict], tasks_pool: List[Dict]):
        self.workers_pool = workers_pool
        # 预清理任务池，移除依赖不完整的任务
        self.tasks_pool = self._clean_task_dependencies(tasks_pool)
        self.algorithm = UniversalAssignmentAlgorithm()
        self.experience_desc = {
            "junior": "初级",
            "intermediate": "中级", 
            "senior": "高级"
        }
        
        print(f"任务池清理完成：原始 {len(tasks_pool)} 个任务 → 清理后 {len(self.tasks_pool)} 个任务")
    
    def _clean_task_dependencies(self, tasks_pool: List[Dict]) -> List[Dict]:
        """预处理：递归清理整个任务池中依赖不完整的任务"""
        task_ids = {t["task_id"] for t in tasks_pool}
        clean_tasks = []
        removed_tasks = set()
        
        # 多轮清理，直到没有新的不完整依赖任务
        max_iterations = 10
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            initial_clean_count = len(clean_tasks)
            clean_tasks = []
            new_removed = set()
            
            for task in tasks_pool:
                task_id = task["task_id"]
                
                # 跳过已经被移除的任务
                if task_id in removed_tasks:
                    continue
                
                dependencies = task.get("dependencies") or []
                # 检查依赖是否都存在且未被移除
                missing_deps = [
                    dep for dep in dependencies 
                    if dep not in task_ids or dep in removed_tasks
                ]
                
                if missing_deps:
                    print(f"第{iteration}轮清理：移除任务 {task_id}，缺少依赖: {missing_deps}")
                    removed_tasks.add(task_id)
                    new_removed.add(task_id)
                else:
                    clean_tasks.append(task)
            
            # 如果这轮没有移除新任务，清理完成
            if not new_removed:
                break
        
        if iteration >= max_iterations:
            print(f"警告：清理任务池达到最大迭代次数 {max_iterations}，可能存在复杂的依赖问题")
        
        return clean_tasks
    
    def generate_random_scenario(self, num_workers: int = 6, num_tasks: int = 3) -> Tuple[List[Dict], List[Dict]]:
        """生成随机场景（选择部分workers和tasks，确保依赖完整性）"""
        
        # Worker选择：随机选择
        available_workers = [w for w in self.workers_pool if w.get("availability_status") == "available"]
        if len(available_workers) < num_workers:
            selected_workers = available_workers + random.sample(
                [w for w in self.workers_pool if w.get("availability_status") != "available"],
                num_workers - len(available_workers)
            )
        else:
            selected_workers = random.sample(available_workers, num_workers)
        
        # Task选择：使用简单的递归依赖逻辑
        selected_tasks = self._select_tasks_simple(num_tasks)
        
        return selected_workers, selected_tasks
    
    def _select_tasks_simple(self, num_tasks: int) -> List[Dict]:
        """
        简单的任务选择逻辑：
        1. 随机选择任务
        2. 递归添加依赖
        3. 重复直到完毕
        """
        if not self.tasks_pool:
            print("警告：任务池为空")
            return []
        
        selected_tasks = []
        selected_ids = set()
        
        print(f"开始选择任务，目标: {num_tasks}个，可用任务池: {len(self.tasks_pool)}个")
        
        while len(selected_tasks) < num_tasks:
            # 1. 随机选择一个还未被选中的任务
            available_tasks = [t for t in self.tasks_pool if t["task_id"] not in selected_ids]
            
            if not available_tasks:
                print("警告：没有更多可选择的任务")
                break
                
            seed_task = random.choice(available_tasks)
            print(f"选择种子任务: {seed_task['task_id']}")
            
            # 2. 递归添加这个任务及其所有依赖
            closure_tasks = self._get_task_and_dependencies(seed_task["task_id"])
            
            # 3. 添加到选择列表中
            added_count = 0
            for task in closure_tasks:
                if task["task_id"] not in selected_ids:
                    selected_tasks.append(task)
                    selected_ids.add(task["task_id"])
                    added_count += 1
                    print(f"  添加任务: {task['task_id']} (依赖: {task.get('dependencies', 'None')})")
            
            print(f"本轮添加了 {added_count} 个任务，当前总数: {len(selected_tasks)}")
        
        # 如果超过了目标数量，直接失败
        if len(selected_tasks) > num_tasks:
            print(f"❌ 任务数量超标：{len(selected_tasks)} > {num_tasks}，本轮生成失败")
            return []  # 返回空列表，让上层重新生成
        
        # 验证依赖完整性（双重保险）
        is_valid = self._validate_task_dependency_completeness(selected_tasks)
        if not is_valid:
            print("❌ 依赖完整性验证失败，本轮生成失败")
            return []  # 返回空列表，让上层重新生成
        
        print(f"任务选择完成，最终选择了 {len(selected_tasks)} 个任务")
        print(f"选择的任务: {[t['task_id'] for t in selected_tasks]}")
        
        return selected_tasks
    
    def _get_task_and_dependencies(self, task_id: str, visited: Set[str] = None) -> List[Dict]:
        """
        递归获取任务及其所有依赖
        
        Args:
            task_id: 任务ID
            visited: 已访问的任务ID集合（避免循环依赖）
            
        Returns:
            任务及其所有依赖的列表
        """
        if visited is None:
            visited = set()
            
        # 避免循环依赖
        if task_id in visited:
            return []
            
        visited.add(task_id)
        
        # 找到当前任务
        task = next((t for t in self.tasks_pool if t["task_id"] == task_id), None)
        if not task:
            print(f"警告：任务 {task_id} 不存在")
            return []
        
        # 结果列表，从当前任务开始
        result = [task]
        
        # 递归添加所有依赖
        dependencies = task.get("dependencies") or []
        for dep_id in dependencies:
            dep_tasks = self._get_task_and_dependencies(dep_id, visited.copy())
            # 避免重复添加
            for dep_task in dep_tasks:
                if not any(t["task_id"] == dep_task["task_id"] for t in result):
                    result.append(dep_task)
        
        return result
    
    def _select_tasks_with_recursive_dependencies(self, num_tasks: int) -> List[Dict]:
        """
        使用递归依赖添加的任务选择逻辑
        
        算法步骤：
        1. 随机选择初始任务
        2. 递归添加每个任务的依赖任务
        3. 直到所有依赖都被添加完毕
        4. 如果任务数量不够，继续随机选择并重复步骤2-3
        5. 智能截取：如果超过目标数量，优先保留依赖完整的任务组合
        """
        if not self.tasks_pool:
            print("警告：任务池为空")
            return []
        
        selected_tasks_set = set()  # 使用set避免重复
        selected_tasks_list = []    # 保持顺序的列表
        closure_groups = []         # 记录每个闭包组合
        
        print(f"开始选择任务，目标: {num_tasks}个，可用任务池: {len(self.tasks_pool)}个")
        
        while len(selected_tasks_list) < num_tasks:
            # 步骤1: 随机选择一个还未被选中的任务作为种子
            available_tasks = [t for t in self.tasks_pool if t["task_id"] not in selected_tasks_set]
            
            if not available_tasks:
                print("警告：没有更多可选择的任务")
                break
                
            seed_task = random.choice(available_tasks)
            print(f"选择种子任务: {seed_task['task_id']}")
            
            # 步骤2: 递归添加这个任务及其所有依赖
            closure_tasks = self._build_recursive_task_closure(seed_task["task_id"])
            
            # 检查添加这个闭包是否会超过目标数量
            new_tasks = [t for t in closure_tasks if t["task_id"] not in selected_tasks_set]
            
            if len(selected_tasks_list) + len(new_tasks) <= num_tasks:
                # 步骤3: 可以完整添加这个闭包
                current_group = []
                for task in new_tasks:
                    selected_tasks_set.add(task["task_id"])
                    selected_tasks_list.append(task)
                    current_group.append(task)
                    print(f"  添加任务: {task['task_id']} (依赖: {task.get('dependencies', 'None')})")
                
                closure_groups.append(current_group)
                print(f"本轮添加了 {len(new_tasks)} 个任务，当前总数: {len(selected_tasks_list)}")
            else:
                # 步骤4: 添加这个闭包会超过目标，需要智能处理
                print(f"添加闭包({len(new_tasks)}个任务)会超过目标，当前{len(selected_tasks_list)}个")
                
                # 优先选择较小的依赖闭包来填充剩余空间
                remaining_slots = num_tasks - len(selected_tasks_list)
                
                if remaining_slots > 0:
                    # 找一个较小的任务（无依赖或依赖很少的）
                    small_candidates = [t for t in available_tasks 
                                      if len(t.get("dependencies") or []) <= remaining_slots - 1]
                    
                    if small_candidates:
                        small_task = random.choice(small_candidates)
                        small_closure = self._build_recursive_task_closure(small_task["task_id"])
                        small_new_tasks = [t for t in small_closure if t["task_id"] not in selected_tasks_set]
                        
                        if len(small_new_tasks) <= remaining_slots:
                            current_group = []
                            for task in small_new_tasks:
                                selected_tasks_set.add(task["task_id"])
                                selected_tasks_list.append(task)
                                current_group.append(task)
                                print(f"  添加任务: {task['task_id']} (依赖: {task.get('dependencies', 'None')})")
                            
                            closure_groups.append(current_group)
                            print(f"本轮添加了 {len(small_new_tasks)} 个任务，当前总数: {len(selected_tasks_list)}")
                        else:
                            print("找不到合适的小闭包，停止添加")
                            break
                    else:
                        print("没有找到合适大小的任务闭包，停止添加")
                        break
                else:
                    break
        
        print(f"任务选择完成，最终选择了 {len(selected_tasks_list)} 个任务")
        print(f"选择的任务: {[t['task_id'] for t in selected_tasks_list]}")
        
        # 验证依赖完整性
        is_valid = self._validate_task_dependency_completeness(selected_tasks_list)
        
        if not is_valid:
            print("⚠️ 依赖完整性验证失败，尝试修复...")
            # 如果验证失败，尝试移除导致问题的任务
            selected_tasks_list = self._fix_task_dependency_issues(selected_tasks_list, closure_groups)
        
        return selected_tasks_list
    
    def _build_recursive_task_closure(self, task_id: str, visited: Set[str] = None) -> List[Dict]:
        """
        递归构建任务的依赖闭包
        
        Args:
            task_id: 起始任务ID
            visited: 已访问的任务ID集合（避免循环依赖）
            
        Returns:
            包含任务及其所有依赖的任务列表
        """
        if visited is None:
            visited = set()
            
        # 避免循环依赖
        if task_id in visited:
            return []
            
        visited.add(task_id)
        
        # 获取当前任务
        task = next((t for t in self.tasks_pool if t["task_id"] == task_id), None)
        if not task:
            print(f"警告：任务 {task_id} 不存在")
            return []
        
        # 结果列表，从当前任务开始
        closure_tasks = [task]
        
        # 递归处理所有依赖
        dependencies = task.get("dependencies") or []
        for dep_id in dependencies:
            dep_closure = self._build_recursive_task_closure(dep_id, visited.copy())
            # 避免重复添加
            for dep_task in dep_closure:
                if not any(t["task_id"] == dep_task["task_id"] for t in closure_tasks):
                    closure_tasks.append(dep_task)
        
        return closure_tasks
    
    def _validate_task_dependency_completeness(self, selected_tasks: List[Dict]) -> bool:
        """验证选择的任务集合中依赖关系是否完整"""
        selected_task_ids = set(t["task_id"] for t in selected_tasks)
        
        missing_dependencies = []
        for task in selected_tasks:
            dependencies = task.get("dependencies") or []
            for dep_id in dependencies:
                if dep_id not in selected_task_ids:
                    missing_dependencies.append(f"任务 {task['task_id']} 依赖缺失的 {dep_id}")
        
        if missing_dependencies:
            print("❌ 依赖完整性验证失败:")
            for missing in missing_dependencies:
                print(f"  - {missing}")
            return False
        else:
            print("✅ 依赖完整性验证通过")
            return True
    
    def _fix_task_dependency_issues(self, selected_tasks: List[Dict], closure_groups: List[List[Dict]]) -> List[Dict]:
        """修复依赖完整性问题"""
        # 找出有问题的任务
        selected_task_ids = set(t["task_id"] for t in selected_tasks)
        problematic_tasks = []
        
        for task in selected_tasks:
            dependencies = task.get("dependencies") or []
            for dep_id in dependencies:
                if dep_id not in selected_task_ids:
                    problematic_tasks.append(task)
                    break
        
        # 按闭包组移除有问题的任务
        for group in reversed(closure_groups):  # 从后往前移除
            group_task_ids = set(t["task_id"] for t in group)
            if any(t["task_id"] in group_task_ids for t in problematic_tasks):
                # 移除这个整个闭包组
                selected_tasks = [t for t in selected_tasks if t["task_id"] not in group_task_ids]
                print(f"移除问题闭包组: {[t['task_id'] for t in group]}")
                # 重新验证
                if self._validate_task_dependency_completeness(selected_tasks):
                    break
        
        return selected_tasks
    def _build_task_closure(self, seed_task_ids: List[str]) -> List[Dict]:
        """构建给定种子任务的依赖闭包 - 保留用于向后兼容"""
        if not seed_task_ids:
            return []
        
        # 使用新的递归闭包构建方法
        all_closure_tasks = []
        seen_task_ids = set()
        
        for seed_id in seed_task_ids:
            closure = self._build_recursive_task_closure(seed_id)
            for task in closure:
                if task["task_id"] not in seen_task_ids:
                    seen_task_ids.add(task["task_id"])
                    all_closure_tasks.append(task)
        
        print(f"构建闭包成功，包含任务: {[t['task_id'] for t in all_closure_tasks]}")
        return all_closure_tasks
    
    def _select_greedy_strategy(self, num_tasks: int) -> List[Dict]:
        """贪心策略：优先选择无依赖或依赖已满足的任务"""
        selected_tasks = []
        selected_ids = set()
        
        # 将任务按优先级排序
        prioritized_tasks = sorted(self.tasks_pool, key=lambda t: (
            t.get('urgency_level', 0) * 10 + 
            t.get('complexity_score', 0)
        ), reverse=True)
        
        for task in prioritized_tasks:
            if len(selected_tasks) >= num_tasks:
                break
                
            task_id = task["task_id"]
            dependencies = task.get("dependencies") or []
            
            # 检查依赖是否都已被选中
            if all(dep_id in selected_ids for dep_id in dependencies):
                selected_tasks.append(task)
                selected_ids.add(task_id)
                print(f"贪心选择任务 {task_id} (依赖: {dependencies if dependencies else '无'})")
        
        print(f"贪心策略完成，选择了 {len(selected_tasks)} 个任务")
        return selected_tasks
    
    def _robust_topological_sort(self, tasks: List[Dict]) -> List[Dict]:
        """健壮的拓扑排序 - 处理循环依赖和缺失依赖"""
        if not tasks:
            return []
        
        task_map = {t["task_id"]: t for t in tasks}
        result = []
        visited = set()
        temp_visited = set()
        
        def visit(task_id: str) -> bool:
            """DFS访问节点，返回True表示成功"""
            if task_id in temp_visited:
                # 检测到循环依赖，记录但不中断
                print(f"检测到循环依赖，涉及任务: {task_id}")
                return False
            
            if task_id in visited:
                return True
            
            # 检查任务是否存在
            task = task_map.get(task_id)
            if not task:
                print(f"拓扑排序时发现任务 {task_id} 不存在，跳过")
                return False
            
            temp_visited.add(task_id)
            
            # 递归访问所有依赖
            dependencies = task.get("dependencies") or []
            for dep_id in dependencies:
                if not visit(dep_id):
                    # 依赖处理失败，但继续处理其他依赖
                    continue
            
            temp_visited.remove(task_id)
            visited.add(task_id)
            result.append(task)
            
            return True
        
        # 访问所有任务
        for task in tasks:
            task_id = task["task_id"]
            if task_id not in visited:
                visit(task_id)
        
        # 检查是否所有任务都被包含
        if len(result) != len(tasks):
            missing_tasks = [t for t in tasks if t["task_id"] not in visited]
            print(f"拓扑排序后缺少 {len(missing_tasks)} 个任务，补充到结果中")
            result.extend(missing_tasks)
        
        # 验证输出顺序是否符合依赖关系
        result_ids = {t["task_id"]: i for i, t in enumerate(result)}
        
        for i, task in enumerate(result):
            dependencies = task.get("dependencies") or []
            for dep_id in dependencies:
                if dep_id in result_ids:
                    dep_index = result_ids[dep_id]
                    if dep_index > i:
                        print(f"警告：任务 {task['task_id']} 出现在依赖 {dep_id} 之前")
        
        print(f"拓扑排序结果顺序: {[t['task_id'] for t in result]}")
        return result
    
    def _simple_topological_sort(self, tasks: List[Dict]) -> List[Dict]:
        """简单的拓扑排序，用于调试显示"""
        task_map = {t["task_id"]: t for t in tasks}
        result = []
        visited = set()
        temp_visited = set()
        
        def visit(task_id: str):
            if task_id in temp_visited:
                # 检测到循环依赖，跳过
                return
            if task_id in visited:
                return
            
            temp_visited.add(task_id)
            
            # 先处理依赖
            task = task_map.get(task_id)
            if task:
                for dep_id in task.get("dependencies") or []:
                    if dep_id in task_map:
                        visit(dep_id)
            
            temp_visited.remove(task_id)
            visited.add(task_id)
            
            if task:
                result.append(task)
        
        for task in tasks:
            if task["task_id"] not in visited:
                visit(task["task_id"])
        
        return result
    
    def generate_qualified_samples(self, target_count: int = 50, max_attempts: int = 1000) -> List[Dict]:
        """生成合格样本（有唯一最优解的场景）"""
        
        qualified_samples = []
        attempt = 0
        
        print(f"开始生成合格样本，目标: {target_count}个，最大尝试: {max_attempts}次")
        print(f"使用优化的任务选择逻辑...")
        
        while len(qualified_samples) < target_count and attempt < max_attempts:
            attempt += 1
            
            print(f"\n--- 第 {attempt} 次尝试 ---")
            
            # 步骤1: 生成随机场景 (workers + tasks，保证依赖完整性)
            workers, tasks = self.generate_random_scenario(
                num_workers=random.randint(4, 8),
                num_tasks=random.randint(2, 5)
            )
            
            print(f"生成场景: {len(workers)}个工作人员, {len(tasks)}个任务")
            
            # 检查是否生成了有效的任务
            if not tasks:
                print("❌ 任务选择失败，跳过此样本")
                continue
            
            # 步骤2: 检查任务处理顺序唯一性
            if not self.algorithm._check_task_processing_order_uniqueness(tasks):
                print("❌ 任务处理顺序不唯一，跳过此样本")
                continue
            
            # 步骤3: 使用规则引擎验证唯一性并生成分配结果
            # 这里会：
            # - 正确处理带依赖关系任务的顺序 (通过优先队列)
            # - 应用分配规则生成结果 
            # - 验证是否有唯一解
            result = self.algorithm.validate_scenario_uniqueness(tasks, workers)
            if len(result) == 4:
                is_unique, assignments, details, updated_workers = result
            else:
                # 兼容旧版本返回值
                is_unique, assignments, details = result
                updated_workers = workers
            
            if is_unique and assignments:
                print(f"✅ 找到合格样本! 分配了 {len(assignments)} 个任务")
                
                # 步骤3: 生成自然语言解释（使用初始状态的workers）
                natural_description = self._generate_natural_description(workers, tasks, assignments, details)
                
                sample = {
                    "scenario_id": f"scenario_{len(qualified_samples):03d}",
                    "workers": workers,
                    "tasks": tasks,
                    "expected_assignments": assignments,
                    "validation_details": details,
                    "natural_language_description": natural_description
                }
                qualified_samples.append(sample)
                
                if len(qualified_samples) % 10 == 0:
                    print(f"已生成 {len(qualified_samples)} 个合格样本...")
            else:
                print(f"❌ 不合格: {details}")
        
        success_rate = len(qualified_samples)/attempt*100 if attempt > 0 else 0
        print(f"\n生成完成！合格样本: {len(qualified_samples)}个，总尝试: {attempt}次，成功率: {success_rate:.1f}%")
        
        return qualified_samples
    
    def _generate_natural_description(self, workers: List[Dict], tasks: List[Dict], assignments: List[Dict], details: str) -> Dict[str, str]:
        """生成场景的自然语言描述"""
        
        # 1. 环境概述
        available_workers = [w for w in workers if w.get("availability_status") == "available"]
        environment_overview = f"总工作人员: {len(workers)}人，其中{len(available_workers)}人可用；待分配任务: {len(tasks)}个"
        
        # 2. 工作人员情况 (显示初始状态)
        workers_summary = []
        for worker in workers:
            if worker.get("availability_status") == "available":
                exp_desc = self.experience_desc.get(worker["experience_level"], worker["experience_level"])
                caps = "、".join(worker["capabilities"])
                # 使用工作人员的初始负载状态，而不是分配后的状态
                # 这里的workers是初始状态的workers，应该已经是分配前的状态
                workload = worker["current_workload_hours"]
                workers_summary.append(f"**{worker['worker_id']}**: {exp_desc}，技能[{caps}]，当前负载{workload}h")
        
        # 3. 任务分析
        tasks_summary = []
        for task in tasks:
            caps = "、".join(task["required_capabilities"])
            urgency = task["urgency_level"]
            complexity = task["complexity_score"]
            hours = task["required_hours"]
            
            # 判断任务类型
            task_type = "常规任务"
            if urgency >= 8:
                task_type = "🔥紧急任务"
            elif complexity >= 7:
                task_type = "🧠复杂任务"
            
            task_desc = f"**{task['task_id']}**: {task_type}，紧急度{urgency}/复杂度{complexity}，需要[{caps}]技能，{hours}h工时"
            if task.get("dependencies"):
                deps = "、".join(task["dependencies"])
                task_desc += f"，依赖[{deps}]"
            tasks_summary.append(task_desc)
        
        # 4. 任务处理顺序逻辑解释
        processing_order_explanation = self._generate_processing_order_explanation(tasks, assignments)
        
        # 5. 预期分配方案
        assignments_summary = []
        
        # 按实际任务分配顺序排序（保持assignments原有顺序，即实际处理顺序）
        sorted_assignments = assignments  # assignments已经是按实际处理顺序生成的
        
        for i, assignment in enumerate(sorted_assignments, 1):
            # 如果有详细描述信息，直接使用
            if "detailed_description" in assignment:
                assignment_desc = {
                    "step": i,
                    "task_id": assignment["task_id"],
                    "worker_id": assignment["worker_id"],
                    **assignment["detailed_description"]
                }
                assignments_summary.append(assignment_desc)
            else:
                # 兼容旧逻辑（应该不会执行到这里）
                task_id = assignment["task_id"]
                worker_id = assignment["worker_id"]
                rationale = assignment["rationale"]
                
                assignments_summary.append({
                    "step": i,
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "rationale": rationale
                })
        
        # 5. 难度评估
        difficulty = "easy"
        urgent_tasks = len([t for t in tasks if t["urgency_level"] >= 8])
        complex_tasks = len([t for t in tasks if t["complexity_score"] >= 7])
        dependent_tasks = len([t for t in tasks if t.get("dependencies")])
        
        if urgent_tasks >= 2 or complex_tasks >= 2 or dependent_tasks >= 2:
            difficulty = "hard"
        elif urgent_tasks >= 1 or complex_tasks >= 1 or dependent_tasks >= 1:
            difficulty = "medium"
        
        # 6. 场景标签
        scenario_tags = []
        if urgent_tasks > 0:
            scenario_tags.append(f"{urgent_tasks}个紧急任务")
        if complex_tasks > 0:
            scenario_tags.append(f"{complex_tasks}个复杂任务")
        if dependent_tasks > 0:
            scenario_tags.append(f"{dependent_tasks}个依赖任务")
        
        scenario_description = f"智能任务分配 - {len(tasks)}任务场景"
        if scenario_tags:
            scenario_description += f"({', '.join(scenario_tags)})"
        
        return {
            "scenario_description": scenario_description,
            "difficulty_level": difficulty,
            "environment_overview": environment_overview,
            "workers_summary": workers_summary,
            "tasks_summary": tasks_summary,
            "task_processing_order_explanation": processing_order_explanation,
            "assignments_detailed": assignments_summary,
            "validation_summary": details,
            "statistics": {
                "total_workers": len(workers),
                "available_workers": len(available_workers),
                "total_tasks": len(tasks),
                "urgent_tasks": urgent_tasks,
                "complex_tasks": complex_tasks,
                "dependent_tasks": dependent_tasks,
                "total_assignments": len(assignments)
            }
        }

    def _generate_processing_order_explanation(self, tasks: List[Dict], assignments: List[Dict]) -> Dict[str, str]:
        """生成任务处理顺序的逻辑解释"""
        
        # 1. 分离有依赖和无依赖任务
        tasks_with_deps = [t for t in tasks if t.get('dependencies')]
        tasks_without_deps = [t for t in tasks if not t.get('dependencies')]
        
        # 2. 基础规则说明
        base_rules = [
            "基于统一配置文件中的task_processing_order规则：",
            "1. 有依赖关系的任务必须等待其依赖任务完成后才能处理",
            "2. 无依赖关系的任务按以下优先级顺序处理：",
            "   - 首先按urgency_level降序排列 (10 > 9 > 8 > ... > 1)",
            "   - urgency_level相同时，按complexity_score降序排列 (10 > 9 > 8 > ... > 1)"
        ]
        
        # 3. 当前场景的具体分析
        scenario_analysis = []
        
        if tasks_without_deps:
            scenario_analysis.append("\n当前场景中的无依赖任务处理顺序：")
            # 按优先级排序无依赖任务，展示处理逻辑
            sorted_independent = sorted(tasks_without_deps, 
                                      key=lambda t: (t.get('urgency_level', 0), t.get('complexity_score', 0)),
                                      reverse=True)
            
            for i, task in enumerate(sorted_independent, 1):
                urgency = task.get('urgency_level', 0)
                complexity = task.get('complexity_score', 0)
                scenario_analysis.append(f"  {i}. {task['task_id']}: 紧急度{urgency}, 复杂度{complexity}")
        
        if tasks_with_deps:
            scenario_analysis.append("\n当前场景中的依赖任务处理逻辑：")
            for task in tasks_with_deps:
                deps = task.get('dependencies', [])
                scenario_analysis.append(f"  - {task['task_id']} 等待 {deps} 完成后处理")
        
        # 4. 实际执行顺序确认
        execution_order = []
        if assignments:
            execution_order.append("\n实际执行顺序验证：")
            for i, assignment in enumerate(assignments, 1):
                task_id = assignment['task_id']
                task = next((t for t in tasks if t['task_id'] == task_id), {})
                urgency = task.get('urgency_level', 0)
                complexity = task.get('complexity_score', 0)
                
                if task.get('dependencies'):
                    deps = task.get('dependencies', [])
                    execution_order.append(f"  {i}. {task_id} (紧急度{urgency}/复杂度{complexity}) - 依赖{deps}已完成")
                else:
                    execution_order.append(f"  {i}. {task_id} (紧急度{urgency}/复杂度{complexity}) - 无依赖，按优先级处理")
        
        return {
            "rules_explanation": "\n".join(base_rules),
            "scenario_analysis": "\n".join(scenario_analysis),
            "execution_verification": "\n".join(execution_order),
            "uniqueness_guarantee": "所有无依赖任务的(urgency_level, complexity_score)组合均唯一，确保处理顺序完全确定，Agent可准确预测。"
        }




def main():
    """主函数 - 生成并验证合格样本"""
    
    # 加载数据池
    print("加载数据池...")
    with open("workers_pool.json", "r", encoding="utf-8") as f:
        workers_pool = json.load(f)
    
    with open("tasks_pool_optimized_final.json", "r", encoding="utf-8") as f:
        tasks_pool = json.load(f)
    
    # 创建场景生成器
    generator = ScenarioGenerator(workers_pool, tasks_pool)
    
    # 生成合格样本
    qualified_samples = generator.generate_qualified_samples(target_count=30, max_attempts=500)
    
    # 保存结果
    with open("qualified_samples.json", "w", encoding="utf-8") as f:
        json.dump(qualified_samples, f, ensure_ascii=False, indent=2)
    
    print(f"合格样本已保存到 qualified_samples.json")
    
    # 显示样本统计
    if qualified_samples:
        sample = qualified_samples[0]
        print(f"\n示例样本:")
        print(f"  工作人员数: {len(sample['workers'])}")
        print(f"  任务数: {len(sample['tasks'])}")
        print(f"  分配方案数: {len(sample['expected_assignments'])}")
        print(f"  验证详情: {sample['validation_details']}")

if __name__ == "__main__":
    main()