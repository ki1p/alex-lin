"""Read-only contact-time advice. Never sends, schedules or edits a message."""
import argparse
import copy
import json
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT=Path(__file__).resolve().parent


def load_policy():
    return json.loads((ROOT/'contact_policy.json').read_text(encoding='utf-8'))


def clock(value):
    if not isinstance(value,str):raise ValueError('Clock time must be HH:MM')
    try:
        parsed=time.fromisoformat(value)
    except ValueError as e:raise ValueError('Invalid clock time: '+value) from e
    if parsed.tzinfo is not None or parsed.second or parsed.microsecond:raise ValueError('Use local HH:MM clock times')
    return parsed


def resolve_zone(name,fallback_minutes=None):
    try:return ZoneInfo(name),'iana'
    except ZoneInfoNotFoundError:
        if fallback_minutes is None:raise ValueError('Timezone data unavailable; install tzdata or provide a verified offset')
        if type(fallback_minutes) is not int or not -840<=fallback_minutes<=840:raise ValueError('Invalid verified UTC offset')
        return timezone(timedelta(minutes=fallback_minutes),name),'verified_fixed_offset_fallback'


def validate_schedule(policy):
    days=policy['working_days']
    if not isinstance(days,list) or not days or any(type(x) is not int or not 0<=x<=6 for x in days) or len(set(days))!=len(days):raise ValueError('working_days must contain unique weekday numbers 0..6')
    windows=policy['contact_windows']
    if not isinstance(windows,list) or not windows:raise ValueError('At least one contact window is required')
    previous=None
    for window in windows:
        if not isinstance(window,list) or len(window)!=2:raise ValueError('Invalid contact window')
        start,end=map(clock,window)
        if start>=end or (previous is not None and start<previous):raise ValueError('Contact windows must be ordered, nonoverlapping, and within one day')
        previous=end
    quiet=policy['quiet_hours']
    if not isinstance(quiet,list) or len(quiet)!=2 or clock(quiet[0])==clock(quiet[1]):raise ValueError('Invalid quiet-hours interval')
    for day in policy.get('unavailable_dates',[])+policy.get('confirmed_working_dates',[]):date.fromisoformat(day)


def in_quiet(value,quiet):
    start,end=map(clock,quiet)
    value=value.time().replace(tzinfo=None)
    return start<=value<end if start<end else value>=start or value<end


def intervals_for_day(day,policy):
    """Contact windows minus quiet hours, so contradictory profiles cannot suggest 23:00."""
    qstart,qend=map(clock,policy['quiet_hours'])
    quiet=[(qstart,qend)] if qstart<qend else [(time.min,qend),(qstart,time.max)]
    pieces=[]
    for start,end in policy['contact_windows']:
        segments=[(clock(start),clock(end))]
        for left,right in quiet:
            next_segments=[]
            for a,b in segments:
                if right<=a or left>=b:next_segments.append((a,b))
                else:
                    if a<left:next_segments.append((a,left))
                    if right<b:next_segments.append((right,b))
            segments=next_segments
        pieces.extend(segments)
    return sorted(pieces)


def day_reason(day,policy,calendar):
    value=day.isoformat()
    if value in policy.get('unavailable_dates',[]):return 'customer_unavailable'
    # A user-confirmed exceptional working date overrides generic public-calendar assumptions.
    if value in policy.get('confirmed_working_dates',[]):return None
    if value in calendar.get('holidays',{}):return 'holiday'
    if day.weekday() not in policy['working_days']:return 'non_working_weekday'
    return None


def plan(country,at=None,channel='email',profile=None,timezone_override=None,policy_data=None):
    data=policy_data or load_policy()
    if country not in data['countries']:raise ValueError('Confirm a supported customer country first: KZ UZ KG TJ TM')
    if channel not in {'email','whatsapp','call'}:raise ValueError('Unsupported channel')
    policy=copy.deepcopy(data['countries'][country])
    profile=profile or {}
    if profile.get('country') and profile['country']!=country:raise ValueError('Profile country conflicts with selected country')
    for key in ['working_days','contact_windows','quiet_hours','unavailable_dates','confirmed_working_dates']:
        if profile.get(key) is not None:policy[key]=profile[key]
    validate_schedule(policy)
    zone_name=timezone_override or profile.get('timezone') or policy['timezone']
    country_zone=zone_name==policy['timezone']
    fallback=profile.get('verified_utc_offset_minutes') if not country_zone else policy['verified_utc_offset_minutes']
    zone,zone_mode=resolve_zone(zone_name,fallback)
    at=at or datetime.now(timezone.utc)
    if at.tzinfo is None or at.utcoffset() is None:raise ValueError('Timestamp must include timezone, e.g. 2026-10-31T23:00:00+05:00')
    local=at.astimezone(zone)
    beijing_zone,_=resolve_zone('Asia/Shanghai',480)
    calendar=data['calendars'].get(country,{}) if country_zone else {}
    if profile.get('holiday_calendar') is not None:calendar=profile['holiday_calendar']
    if not isinstance(calendar,dict) or not isinstance(calendar.get('holidays',{}),dict):raise ValueError('Invalid holiday calendar')
    for day in calendar.get('holidays',{}):date.fromisoformat(day)
    warnings=[]
    if not profile.get('schedule_confirmed',False):warnings.append('企业作息未确认；联系窗口和周一至周五为保守实践建议，不是全国统一作息。')
    if not country_zone:warnings.append('客户可能在出差地；未自动套用原国家节假日，需核对其当前所在地日历。')
    coverage=calendar.get('coverage_years',[])
    if local.year not in coverage:warnings.append(f'{local.year}年的节假日未收录，候选时间需要再次核验。')
    if not calendar.get('complete',False):warnings.append('节假日日历是已查日期的参考快照，可能遗漏调休、宗教日期变化或企业休假。')
    if local.date().isoformat() in calendar.get('possible_working_dates',[]):warnings.append('资料提示该日可能调为工作日，需客户确认；未据此自动取消周末保护。')
    if zone_mode!='iana':warnings.append('系统缺少IANA时区数据，使用版本化已核对UTC偏移；安排远期联系前复核。')
    checked=date.fromisoformat(data['checked_on'])
    if abs((local.date()-checked).days)>366:warnings.append('所选日期距资料核对日期较远，请重新核对时区和工作日历。')
    reason=day_reason(local.date(),policy,calendar)
    if in_quiet(local,policy['quiet_hours']):reason='quiet_hours'
    elif reason is None and not any(a<=local.time().replace(tzinfo=None)<b for a,b in intervals_for_day(local.date(),policy)):reason='outside_contact_window'
    okay=reason is None
    candidate=local if okay else None
    if not okay:
        for offset in range(371):
            day=local.date()+timedelta(days=offset)
            if day_reason(day,policy,calendar):continue
            for start,end in intervals_for_day(day,policy):
                point=datetime.combine(day,start,tzinfo=zone)
                # Round-trip through UTC to avoid proposing a nonexistent DST wall time.
                point=point.astimezone(timezone.utc).astimezone(zone)
                finish=datetime.combine(day,end,tzinfo=zone)
                if point.date()!=day or not start<=point.time().replace(tzinfo=None)<end:continue
                if day==local.date() and point.astimezone(timezone.utc)<local.astimezone(timezone.utc):
                    if local.astimezone(timezone.utc)<finish.astimezone(timezone.utc):point=local
                    else:continue
                if not in_quiet(point,policy['quiet_hours']):candidate=point;break
            if candidate is not None:break
    reasons={'quiet_hours':'已进入默认或客户确认的免打扰时段，可能正在休息，建议不要现在联系。','outside_contact_window':'目前不在建议联系窗口，可能处于用餐、通勤或下班时间。','holiday':'参考日历将今天列为假日，建议顺延。','non_working_weekday':'按当前配置，今天属于非工作日。','customer_unavailable':'客户已告知该日不方便联系。'}
    result={'country':country,'channel':channel,'timezone':zone_name,'timezone_mode':zone_mode,'local_now':local.isoformat(timespec='minutes'),'beijing_now':at.astimezone(beijing_zone).isoformat(timespec='minutes'),'status':'within_contact_window' if okay else reason,'recommendation':'可以在此候选窗口联系；仍以客户偏好及真实事项为准。' if okay else reasons[reason],'contact_windows':policy['contact_windows'],'quiet_hours':policy['quiet_hours'],'schedule_confirmed':bool(profile.get('schedule_confirmed',False)),'calendar_checked_on':calendar.get('checked_on'),'calendar_complete':calendar.get('complete',False),'warnings':warnings,'automatically_sent':False,'automatically_scheduled':False}
    if candidate is not None:
        result['next_candidate_local']=candidate.isoformat(timespec='minutes')
        result['next_candidate_beijing']=candidate.astimezone(beijing_zone).isoformat(timespec='minutes')
        if candidate.year not in coverage and not any(str(candidate.year) in w for w in warnings):warnings.append(f'候选日期进入{candidate.year}年，其节假日尚未核验。')
    else:result['warnings'].append('没有找到可用窗口，请核对客户作息与免打扰配置。')
    action={'email':'发送邮件','whatsapp':'发送消息','call':'拨打电话'}[channel]
    if local.hour==23 and not okay:result['reminder_zh']=f'客户当地现在是{local:%Y-%m-%d %H:%M}，已是深夜，建议不要打扰；先准备内容，在下一个合适工作窗口再{action}。'
    else:result['reminder_zh']=f'客户当地时间{local:%Y-%m-%d %H:%M}。'+result['recommendation']
    return result


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description='客户联系时间建议：只读判断，不发送、不建立定时任务')
    p.add_argument('--country',required=True,choices=['KZ','UZ','KG','TJ','TM'])
    p.add_argument('--at',help='带时区ISO时间；默认使用当前UTC时间')
    p.add_argument('--timezone',help='客户已确认的当前所在地IANA时区，如Asia/Dubai')
    p.add_argument('--channel',choices=['email','whatsapp','call'],default='email')
    p.add_argument('--profile',type=Path,help='本地私人作息JSON；不要上传真实客户资料')
    a=p.parse_args()
    try:
        at=datetime.fromisoformat(a.at.replace('Z','+00:00')) if a.at else None
        profile=json.loads(a.profile.read_text(encoding='utf-8')) if a.profile else None
        print(json.dumps(plan(a.country,at,a.channel,profile,a.timezone),ensure_ascii=False,indent=2))
    except (ValueError,OSError,TypeError,KeyError) as e:p.exit(1,str(e)+'\n')


if __name__=='__main__':main()
