"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { 
  Home, 
  Search, 
  Settings, 
  Plus, 
  FileText, 
  History,
  User,
  LogOut,
  MessageCircle,
  Brain,
  BookOpen
} from "lucide-react";
import { useRouter, usePathname } from "next/navigation";

export const Sidebar = () => {
  const [activeItem, setActiveItem] = useState('eduthum');
  const router = useRouter();
  const pathname = usePathname();

  const navigationItems = [
    {
      id: 'eduthum',
      label: 'Eduthum',
      icon: Brain,
      href: '/dashboard/Eduthum'
    },
    {
      id: 'darshan',
      label: 'Darshan AI',
      icon: MessageCircle,
      href: '/dashboard/ReligiousAI'
    }
  ];



  const handleNavigation = (item) => {
    setActiveItem(item.id);
    if (item.href) {
      router.push(item.href);
    }
  };

  const isActive = (itemHref) => {
    return pathname === itemHref || (itemHref === '/dashboard' && pathname === '/');
  };

  return (
    <div className="w-64 bg-zinc-900 flex flex-col h-full">


      {/* Main Navigation */}
      <div className="flex-1 flex flex-col p-4 space-y-2">
        <div className="mb-4">
          <h3 className="text-zinc-500 text-xs uppercase font-semibold mb-3 px-2">
            AI Assistants
          </h3>
          {navigationItems.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.href);
            
            return (
              <Button
                key={item.id}
                variant="ghost"
                className={`w-full justify-start h-auto p-3 text-left ${
                  active
                    ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                    : 'text-zinc-400 hover:text-white hover:bg-zinc-800'
                }`}
                onClick={() => handleNavigation(item)}
              >
                <div className="flex items-center space-x-3 w-full">
                  <Icon className="h-5 w-5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium">{item.label}</div>
                    {/* {item.description && (
                      <div className={`text-xs ${
                        active ? 'text-indigo-100' : 'text-white'
                      }`}>
                        {item.description}
                      </div>
                    )} */}
                  </div>
                </div>
              </Button>
            );
          })}
        </div>

        

        {/* Quick Actions */}
       
      </div>

      {/* Bottom Section */}
      
    </div>
  );
};