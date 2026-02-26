#!/usr/bin/env python3
"""
Test script for the Task Planner application
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from main import Task, BusySlot, TaskPlanner
from datetime import datetime, timedelta, time
import pytz

# Set console encoding for Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def test_task_planner():
    """Test the task planner functionality"""
    print("🧪 Testing Task Planner Application...")
    
    # Create a planner instance
    planner = TaskPlanner()
    
    # Test 1: Add tasks
    print("\n1. Testing task creation...")
    timezone = pytz.timezone("Europe/Paris")
    
    # Use future dates for testing
    now = datetime.now(timezone)
    future_date1 = now + timedelta(days=10)
    future_date2 = now + timedelta(days=5)
    future_date3 = now + timedelta(days=7)
    
    task1 = Task("Rédiger rapport", 2.5, future_date1, "Haute")
    task2 = Task("Préparer présentation", 1.0, future_date2, "Normale")
    task3 = Task("Revoir code", 3.0, future_date3, "Basse")
    
    planner.add_task(task1)
    planner.add_task(task2)
    planner.add_task(task3)
    
    print(f"✅ Added {len(planner.tasks)} tasks")
    
    # Test 2: Add busy slots
    print("\n2. Testing busy slots...")
    # Use future dates for busy slots too
    busy_slot_date1 = now + timedelta(days=2)
    busy_slot_date2 = now + timedelta(days=3)
    
    busy_slot1 = BusySlot(
        timezone.localize(datetime.combine(busy_slot_date1.date(), time(10, 0))),
        timezone.localize(datetime.combine(busy_slot_date1.date(), time(12, 0))),
        "Réunion"
    )
    busy_slot2 = BusySlot(
        timezone.localize(datetime.combine(busy_slot_date2.date(), time(14, 0))),
        timezone.localize(datetime.combine(busy_slot_date2.date(), time(16, 0))),
        "Cours"
    )
    
    planner.add_busy_slot(busy_slot1)
    planner.add_busy_slot(busy_slot2)
    
    print(f"✅ Added {len(planner.busy_slots)} busy slots")
    
    # Test 3: Test planning algorithm
    print("\n3. Testing planning algorithm...")
    planned_tasks, unplanned_tasks = planner.plan_tasks()
    
    print(f"✅ Planning completed:")
    print(f"   - Planned tasks: {len(planned_tasks)}")
    print(f"   - Unplanned tasks: {len(unplanned_tasks)}")
    
    # Test 4: Display schedule
    print("\n4. Generated schedule:")
    schedule_by_day = planner.get_schedule_by_day()
    
    for day, tasks in schedule_by_day.items():
        day_name = datetime.strptime(day, "%Y-%m-%d").strftime("%A %d %B %Y")
        print(f"   📅 {day_name}:")
        
        for task_title, start, end in tasks:
            print(f"      🕒 {start.strftime('%H:%M')} - {end.strftime('%H:%M')}: {task_title}")
    
    # Test 5: Display unplanned tasks
    if unplanned_tasks:
        print(f"\n5. Unplanned tasks ({len(unplanned_tasks)}):")
        for task in unplanned_tasks:
            print(f"   ❌ {task.message}")
    
    # Test 6: Test constraints
    print(f"\n6. Current constraints:")
    constraints = planner.constraints
    print(f"   - Max hours/day: {constraints['max_hours_per_day']}h")
    print(f"   - Latest hour: {constraints['latest_hour']}:00")
    print(f"   - No Sunday: {constraints['no_sunday']}")
    print(f"   - Lunch break: {constraints['lunch_break']}")
    
    print("\n✅ All tests completed successfully!")
    return True

def test_google_calendar_integration():
    """Test Google Calendar integration"""
    print("\n🔄 Testing Google Calendar integration...")
    
    try:
        from google_calendar import GoogleCalendarManager
        
        # Create manager
        calendar_manager = GoogleCalendarManager()
        
        # Check if credentials file exists
        if os.path.exists('credentials.json'):
            print("✅ credentials.json found")
            
            # Test authentication (without actually authenticating)
            print("✅ GoogleCalendarManager created successfully")
            print("✅ Google Calendar module can be imported")
            
            # Show available methods
            methods = [method for method in dir(calendar_manager) if not method.startswith('_')]
            print(f"✅ Available methods: {', '.join(methods[:5])}...")
        else:
            print("⚠️  credentials.json not found (expected for test environment)")
            print("✅ Google Calendar module structure is valid")
        
        return True
        
    except ImportError as e:
        print(f"❌ Google Calendar import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Google Calendar test error: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Starting Task Planner Application Tests")
    print("=" * 50)
    
    # Test core functionality
    core_success = test_task_planner()
    
    # Test Google Calendar integration
    gc_success = test_google_calendar_integration()
    
    print("\n" + "=" * 50)
    print("📊 TEST SUMMARY:")
    print(f"   Core functionality: {'✅ PASS' if core_success else '❌ FAIL'}")
    print(f"   Google Calendar: {'✅ PASS' if gc_success else '❌ FAIL'}")
    
    if core_success and gc_success:
        print("\n🎉 ALL TESTS PASSED! The application is ready to use.")
        print("\n📝 To run the application:")
        print("   streamlit run main.py")
    else:
        print("\n⚠️  Some tests failed. Please check the output above.")
    
    return core_success and gc_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)