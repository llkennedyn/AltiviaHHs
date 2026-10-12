"""Read the cost matrix without fixed column/row bounds or silent omissions."""
import io
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


def normalized(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD',str(value or '').casefold()) if not unicodedata.combining(c)).split())


def edt(value):
    if value is None or isinstance(value,bool):return ''
    if isinstance(value,(int,float)):
        number=Decimal(str(value))
        return str(int(number)) if number.is_finite() and number==number.to_integral_value() else ''
    value=str(value).strip()
    return value if re.fullmatch(r'\d+(?:[.\-]\d+)*',value) else ''


def vertical_total(formula,row):
    """Aggregates of other rows are summaries; horizontal sums may be work."""
    if not isinstance(formula,str) or not formula.startswith('='):return False
    if not re.search(r'\b(?:SUM|SUBTOTAL|SUMIF|SUMIFS|AGGREGATE)\s*\(',formula,re.I):return False
    refs=re.findall(r'(?<![\w!])\$?[A-Z]{1,3}\$?(\d+)',formula.upper())
    return bool(refs) and any(int(r)!=row for r in refs)


def read_matrix(payload):
    values=load_workbook(io.BytesIO(payload),read_only=True,data_only=True)
    formulas=load_workbook(io.BytesIO(payload),read_only=True,data_only=False)
    try:
        if 'Estimado de Costos' not in values.sheetnames:raise ValueError('No existe la hoja Estimado de Costos.')
        ws=values['Estimado de Costos'];fs=formulas['Estimado de Costos']
        # Materialize once: repeated random reads on read-only sheets are quadratic.
        rows=list(ws.iter_rows(values_only=True));raw=list(fs.iter_rows(values_only=True))
        get=lambda data,r,c:data[r-1][c-1] if r<=len(data) and c<=len(data[r-1]) else None
        candidates=[];positions=[];persons=[];canonical_names={};excluded=[];review=[];errors=[];source_total=None
        for col in range(10,ws.max_column+1):
            name=str(get(rows,5,col) or '').strip();role=str(get(rows,4,col) or '').strip()
            if not name and not role:
                has_data=any(edt(get(rows,r,2)) and str(get(rows,r,3) or '').strip() and isinstance(get(rows,r,col),(int,float)) and not isinstance(get(rows,r,col),bool) and get(rows,r,col)>0 for r in range(10,len(rows)+1))
                if not has_data:continue
                role='Puesto sin encabezado'
            placeholder=normalized(name) in ('','tbd','por definir','por asignar','pendiente','n/a','na','-')
            if not placeholder and not isinstance(get(rows,5,col),str):
                errors.append(f'{get_column_letter(col)}5: el nombre del profesional debe ser texto.');continue
            if not placeholder:
                name=canonical_names.setdefault(normalized(name),name)
                persons.append((col,name))
            positions.append(dict(column=col,letter=get_column_letter(col),name='' if placeholder else name,role=role,unassigned=placeholder))
        if not positions:errors.append('No se detectaron profesionales o puestos en la fila 5, desde J.')
        for index in range(10,len(rows)+1):
            code=edt(get(rows,index,2));title=str(get(rows,index,3) or '').strip()
            label=normalized(str(get(rows,index,2) or '')+' '+title)
            if re.match(r'^(?:horas? totales?|total (?:de )?horas?|costo total|coste total|total costos?|descuento comercial)\b',label):
                if re.match(r'^(?:horas? totales?|total (?:de )?horas?)\b',label):
                    total_values=[get(rows,index,p['column']) for p in positions]
                    if all(v is None or isinstance(v,(int,float)) and not isinstance(v,bool) for v in total_values):
                        source_total=sum(Decimal(str(v or 0)) for v in total_values)
                excluded.append(dict(row=index,code=code,name=title or str(get(rows,index,2)),reason='Total de horas / costos; no es una actividad'));continue
            if not title:
                if code:errors.append(f'Fila {index}: EDT {code} sin nombre de actividad.')
                continue
            preceding_blank=index==10 or not any(str(v or '').strip() for v in rows[index-2])
            following=next((edt(get(rows,r,2)) for r in range(index+1,len(rows)+1) if edt(get(rows,r,2))),None)
            section=code.endswith('000') and preceding_blank
            if section or any(vertical_total(get(raw,index,p['column']),index) for p in positions):
                excluded.append(dict(row=index,code=code,name=title,reason='Resumen general / suma de subtareas'));continue
            cross={};names={};budget=0;unassigned=0;has_hours=False
            for p in positions:
                col=p['column'];value=get(rows,index,col);formula=get(raw,index,col)
                if value is None and isinstance(formula,str) and formula.startswith('='):
                    errors.append(f'{p["letter"]}{index}: fórmula sin resultado guardado. Recalcula y guarda el libro en Excel.');continue
                if value is None or (isinstance(value,str) and not value.strip()):continue
                try:
                    if isinstance(value,bool):raise InvalidOperation
                    q=Decimal(str(value))*4
                    if not q.is_finite() or q<0 or q!=q.to_integral_value():raise InvalidOperation
                except (InvalidOperation,ValueError):
                    errors.append(f'{p["letter"]}{index}: HH inválidas ({value}); usa valores no negativos en múltiplos de 0.25.');continue
                if not q:continue
                has_hours=True;budget+=int(q)
                if p['unassigned']:unassigned+=int(q)
                else:
                    key=normalized(p['name']);names.setdefault(key,p['name']);cross[key]=cross.get(key,0)+int(q)
            item=dict(row=index,code=code,name=title,cross=[(names[k],q) for k,q in cross.items()],budget=budget,unassigned=unassigned)
            if not code:
                if has_hours:review.append(item)
                continue
            # Only true hierarchy parents are omitted, not every EDT ending in 00.
            parent=code.endswith('0') and following and following!=code and following.startswith(code.rstrip('0'))
            if parent and not has_hours:
                excluded.append(dict(row=index,code=code,name=title,reason='Encabezado de subtareas sin HH propias'));continue
            candidates.append(item)
        codes=[r['code'] for r in candidates]
        if len(codes)!=len(set(codes)):errors.append('Hay códigos EDT repetidos en las actividades. Corrígelos antes de importar.')
        if not candidates and not review:errors.append('No se encontraron actividades para importar.')
        return dict(persons=persons,positions=positions,activities=candidates,review=review,excluded=excluded,errors=errors,source_total=source_total,last_column=max((p['column'] for p in positions),default=10),last_row=len(rows))
    finally:
        values.close();formulas.close()


def resolve_review(matrix,decisions):
    result=[dict(r) for r in matrix['activities']]
    for item,choice in zip(matrix['review'],decisions):
        if choice['Incluir']:
            code=edt(choice['EDT'])
            if not code:raise ValueError(f'Fila {item["row"]}: asigna un EDT válido para incluirla.')
            result.append(dict(item,code=code))
    codes=[r['code'] for r in result]
    if len(codes)!=len(set(codes)):raise ValueError('Hay códigos EDT repetidos entre las actividades seleccionadas.')
    return result
