import { redirect } from 'next/navigation';
import { isAuthenticated } from '@/lib/auth';
import Dashboard from '@/components/Dashboard';

export default async function HomePage() {
  if (!(await isAuthenticated())) {
    redirect('/login');
  }
  
  return <Dashboard />;
}
