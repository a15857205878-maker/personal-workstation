export function acceptBrief(text,limit){
 if(typeof text!=='string'||!text.trim())throw Error('请先填写任务需求。');
 if(text.length>limit)throw Error(`内容超过${limit}字符，请先精简；不会自动截断。`);
 return text;
}
export function advancedBrief({form,task}){
 const value=task||form||{};
 return ['请协助澄清或接手以下任务，先拟定可直接发布的任务要求：目标、约束、交付物、验收标准；缺少信息时明确列出。',
 value.title&&'任务：'+value.title,value.instruction&&'原需求：\n'+value.instruction,
 value.materials&&'资料：\n'+value.materials,value.attachments_text&&'附件识别文字（仅文字，未传原件）：\n'+value.attachments_text,value.requirements&&'补充要求：\n'+value.requirements,
 value.result&&'已有结果（未经重新核验）：\n'+value.result,value.error&&'遇到的问题：\n'+value.error,
 value.attachments_text?'仅包含这里展示的文字与附件识别文字；未传附件原件，不得声称已核验图像或完成软件操作。':'仅包含这里展示的文字，未读取附件；不得声称已经完成软件操作或文件修改。'].filter(Boolean).join('\n\n');
}
export function importTask(form,text,replace=false){
 acceptBrief(text,24000);
 if(!replace&&[form.instruction,form.materials,form.requirements].some(v=>v?.trim()))throw Error('当前草稿已有内容，请明确确认替换，或复制后手动粘贴。');
 return {...form,instruction:text,materials:'',requirements:''};
}
