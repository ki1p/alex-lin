import copy
import unittest
from datetime import datetime,timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError
import contact_planner as cp

def run(c,at,**kw):return cp.plan(c,datetime.fromisoformat(at),**kw)

class ContactTests(unittest.TestCase):
    def test_all_18_markets_have_policies(self):
        self.assertEqual(set(cp.load_policy()['countries']),{'SA','AE','IN','ID','PH','BD','EG','MA','KE','TZ','RW','ET','VN','KZ','UZ','KG','TJ','TM'})
    def test_india_half_hour_and_late_night_rollover(self):
        p=run('IN','2026-10-31T23:00:00+05:30')
        self.assertEqual(p['status'],'quiet_hours')
        self.assertIn('23:00',p['reminder_zh'])
        self.assertEqual(p['beijing_now'],'2026-11-01T01:30+08:00')
        self.assertEqual(p['next_candidate_local'],'2026-11-02T09:30+05:30')
        self.assertEqual(p['next_candidate_beijing'],'2026-11-02T12:00+08:00')
    def test_indonesia_requires_city_timezone(self):
        with self.assertRaisesRegex(ValueError,'multiple time zones'):run('ID','2026-11-02T01:00:00+00:00')
    def test_three_indonesian_zones(self):
        for zone,hour in [('Asia/Jakarta',7),('Asia/Makassar',8),('Asia/Jayapura',9)]:
            p=run('ID','2026-11-02T00:00:00+00:00',timezone_override=zone)
            local=datetime.fromisoformat(p['local_now'])
            self.assertEqual(local.utcoffset(),timedelta(hours=hour))
            self.assertFalse(any('出差地' in w for w in p['warnings']))
    def test_saudi_friday_closed_but_sunday_open(self):
        p=run('SA','2026-11-06T10:00:00+03:00')
        self.assertEqual(p['status'],'non_working_weekday')
        self.assertEqual(p['next_candidate_local'],'2026-11-08T09:30+03:00')
        self.assertEqual(run('SA','2026-11-08T10:00:00+03:00')['status'],'within_contact_window')
    def test_uae_friday_morning_open(self):
        self.assertEqual(run('AE','2026-11-06T10:00:00+04:00')['status'],'within_contact_window')
    def test_uae_friday_afternoon_defers(self):
        p=run('AE','2026-11-06T14:00:00+04:00')
        self.assertEqual(p['status'],'outside_contact_window')
        self.assertEqual(p['next_candidate_local'],'2026-11-09T09:30+04:00')
    def test_confirmed_customer_schedule_overrides_friday_default(self):
        profile={'schedule_confirmed':True,'working_days':[4],'contact_windows':[['14:00','16:00']]}
        self.assertEqual(run('AE','2026-11-06T15:00:00+04:00',profile=profile)['status'],'within_contact_window')
    def test_bangladesh_late_thursday_waits_until_sunday(self):
        p=run('BD','2026-11-05T23:00:00+06:00')
        self.assertEqual(p['next_candidate_local'],'2026-11-08T09:30+06:00')
    def test_egypt_summer_and_winter_offsets(self):
        a=run('EG','2026-03-01T10:00:00+00:00');b=run('EG','2026-07-01T10:00:00+00:00')
        self.assertEqual(datetime.fromisoformat(a['local_now']).utcoffset(),timedelta(hours=2))
        self.assertEqual(datetime.fromisoformat(b['local_now']).utcoffset(),timedelta(hours=3))
    def test_morocco_ramadan_clock_change(self):
        a=run('MA','2026-02-20T10:00:00+00:00');b=run('MA','2026-04-01T10:00:00+00:00')
        self.assertEqual(datetime.fromisoformat(a['local_now']).utcoffset(),timedelta(0))
        self.assertEqual(datetime.fromisoformat(b['local_now']).utcoffset(),timedelta(hours=1))
    def test_no_fixed_fallback_for_dynamic_zones(self):
        with patch.object(cp,'ZoneInfo',side_effect=ZoneInfoNotFoundError):
            for zone in ['Africa/Cairo','Africa/Casablanca']:
                with self.assertRaisesRegex(ValueError,'Dynamic timezone'):cp.resolve_zone(zone,120)
    def test_unknown_holiday_calendar_is_visible(self):
        p=run('RW','2026-11-02T10:00:00+02:00')
        self.assertFalse(p['calendar_complete'])
        self.assertTrue(any('2026' in w for w in p['warnings']))
    def test_no_actual_sending_or_scheduling(self):
        p=run('PH','2026-11-02T10:00:00+08:00')
        self.assertFalse(p['automatically_sent']);self.assertFalse(p['automatically_scheduled'])
    def test_old_central_asia_regression(self):
        p=run('KZ','2026-10-31T23:00:00+05:00')
        self.assertEqual(p['next_candidate_local'],'2026-11-02T09:30+05:00')
        self.assertEqual(p['next_candidate_beijing'],'2026-11-02T12:30+08:00')
    def test_all_original_markets_still_run(self):
        for c in ['KZ','UZ','KG','TJ','TM','VN']:
            self.assertIn('next_candidate_local',run(c,'2026-11-02T03:00:00+00:00'))
    def test_customer_unavailable_overrides_workday(self):
        p=run('KE','2026-11-02T10:00:00+03:00',profile={'unavailable_dates':['2026-11-02']})
        self.assertEqual(p['status'],'customer_unavailable')
        self.assertTrue(p['next_candidate_local'].startswith('2026-11-03'))
    def test_exceptional_workday_overrides_weekend(self):
        p=run('SA','2026-11-06T10:00:00+03:00',profile={'confirmed_working_dates':['2026-11-06']})
        self.assertEqual(p['status'],'within_contact_window')
    def test_trip_does_not_copy_home_holidays(self):
        p=run('SA','2026-11-02T10:00:00+04:00',timezone_override='Asia/Dubai')
        self.assertTrue(any('出差地' in w for w in p['warnings']))
        self.assertFalse(p['calendar_complete'])
    def test_invalid_naive_timestamp(self):
        with self.assertRaisesRegex(ValueError,'Timestamp must include timezone'):cp.plan('KE',datetime(2026,11,2,10))
    def test_invalid_overlapping_windows_rejected(self):
        with self.assertRaisesRegex(ValueError,'ordered, nonoverlapping'):
            run('KE','2026-11-02T10:00:00+03:00',profile={'contact_windows':[['09:00','12:00'],['11:00','13:00']]})
    def test_quiet_hours_trim_contradictory_windows(self):
        p=run('KE','2026-11-02T23:00:00+03:00',profile={'contact_windows':[['21:00','23:30']]})
        self.assertEqual(p['status'],'quiet_hours')
        self.assertEqual(p['next_candidate_local'],'2026-11-03T21:00+03:00')
    def test_mismatched_profile_country_rejected(self):
        with self.assertRaisesRegex(ValueError,'conflicts'):run('PH','2026-11-02T10:00:00+08:00',profile={'country':'VN'})
    def test_no_mutation_of_policy(self):
        data=cp.load_policy();before=copy.deepcopy(data)
        run('AE','2026-11-06T14:00:00+04:00',profile={'working_days':[0,1]},policy_data=data)
        self.assertEqual(data,before)

if __name__=='__main__':unittest.main()
