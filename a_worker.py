import time
import schedule
from rich.console import Console
from a import main as process_feeds

console = Console()

def job():
    """Run the RSS feed processing job"""
    try:
        console.print("[green]Starting scheduled RSS feed processing...[/green]")
        process_feeds()
        console.print("[green]Completed scheduled RSS feed processing[/green]")
    except Exception as e:
        console.print(f"[red]Error in scheduled job: {e}[/red]")

def run_worker():
    """Run the worker with scheduled jobs"""
    console.print("[blue]Starting RSS feed worker...[/blue]")
    
    # Schedule the job to run every hour
    schedule.every(1).hours.do(job)
    
    # Run the job immediately on startup
    job()
    
    # Keep the worker running
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Check every minute for pending jobs
        except KeyboardInterrupt:
            console.print("[yellow]Worker shutdown requested...[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Worker error: {e}[/red]")
            # Wait a bit before retrying
            time.sleep(300)  # 5 minutes
    
    console.print("[blue]Worker stopped[/blue]")

if __name__ == "__main__":
    run_worker() 