"""The fixed workstation walkthrough and its offline Word document."""

from base64 import b64encode

from task_station.document_export import document_bytes


def task():
    return {
        'title': '本周三步工作计划',
        'file_name': '示例-本周三步工作计划.docx',
        'goal': '请把周一整理资料、周三核对进度、周五提交文档做成一份 Word 计划。',
        'table': {
            'columns': ['日期', '安排'],
            'rows': [['周一', '整理资料'], ['周三', '核对进度'], ['周五', '提交文档']],
        },
        'jobs': [
            {'title': '整理每周安排', 'instruction': '把三条事项按日期排列，保留全部原文。',
             'owner': '整理搭档', 'output_format': 'text'},
            {'title': '生成 Word 文档', 'instruction': '用带表头的两列表格呈现三条安排。',
             'owner': '文档搭档', 'output_format': 'docx'},
        ],
    }


def document():
    sample = task()
    table = sample['table']
    rows = [table['columns'], ['---'] * len(table['columns']), *table['rows']]
    markdown = '\n'.join([f"# {sample['title']}", '',
                          *(' | '.join(row) for row in rows)])
    return {'name': sample['file_name'],
            'mime': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'content_base64': b64encode(document_bytes(markdown)).decode('ascii')}
