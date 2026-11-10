import { redirect } from 'next/navigation'

export default function SpendingRedirect() {
  redirect('/transactions')
}
