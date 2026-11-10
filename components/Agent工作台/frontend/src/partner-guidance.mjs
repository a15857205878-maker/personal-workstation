// Operation guidance only, never generated model speech.
export function partnerGuidance(status,options={}){
 const aliases={'草稿':'draft','排队中':'queued','执行中':'running','等待交接':'waiting_handoff','需要用户处理':'needs_user','结果待确认':'awaiting_confirmation','已完成':'completed','失败':'failed','已取消':'cancelled','需要检查':'needs_check'};
 const state=aliases[status]||status;
 if(options.archived)return '这份任务已归档。先回看内容，需要继续时再恢复记录。';
 if(options.history)return '这是一份已保存的协作记录。先核对回复与状态，再根据可用操作继续。';
 if(options.readOnly)return '这是只读的历史记录。可以回看回复，再返回当前协作。';
 if(options.manual&&['draft','waiting_handoff','needs_user'].includes(state))return '目标已保存，接下来需要在电脑客户端完成交接。';
 return ({draft:'先检查目标与参考材料，确认清楚后再开始处理。',queued:'任务已排队，轮到它时会更新进度，请不要重复提交。',running:'电脑正在处理，进度会在这里更新。可以补充要求，请不要重复提交。',stopping:'正在请求停止，先等状态更新。已发出的请求可能仍计费。',waiting_handoff:'目标已保存，接下来需要在电脑客户端完成交接。',needs_user:'这一步需要你处理。先看任务说明与记录，再继续交接。',awaiting_confirmation:'回复已经回来，先看看结果，符合预期后再确认完成。',completed:'本次记录已完成。先看看回复和成果，需要调整时再继续。',failed:'这次处理遇到了问题。先看看错误说明，再决定重试还是调整要求。',cancelled:'这次处理已取消。记录会保留，可以先核对已产生的内容。',interrupted:'上次处理已中断。先核对实际进度，再决定后续处理。',needs_check:'这项任务需要核对。先看错误或处理记录，确认实际进度。'})[state]||'先核对当前状态与记录，再决定下一步。';
}
