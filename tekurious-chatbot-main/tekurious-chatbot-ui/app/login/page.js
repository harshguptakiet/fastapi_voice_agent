"use client";

import Image from "next/image";
import Head from "next/head";
import { useState } from 'react';

import { useDispatch } from 'react-redux';
import { login } from '@/app/store/authSlice';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';

export default function Login() {
  const dispatch = useDispatch();
  const router = useRouter();
  const { register, handleSubmit, formState: { errors } } = useForm();
   const [error, setError] = useState('');

  const onSubmit = (data) => {
       setError('');
    if (data.email === "yashgoel711@gmail.com" && data.password === "12345678") {
      dispatch(login());
      router.push('/dashboard/ReligiousAI');
    } else {
       setError("Invalid email or password.");
      alert("Invalid credentials");
    }
  };

  return (
    <>
      <Head>
        <title>Login</title>
      </Head>

      {/* Background Split */}
      <div className="min-h-screen relative flex items-center justify-center">
        {/* Top Half - Gradient */}
        <div className="absolute top-0 left-0 w-full h-1/2 bg-gradient-to-r from-blue-500 to-indigo-500" />

        {/* Bottom Half - White */}
        <div className="absolute bottom-0 left-0 w-full h-1/2 bg-white" />

        {/* Login Card */}
        <div className="relative z-10 w-full max-w-4xl bg-white rounded-xl shadow-xl flex overflow-hidden">
          {/* Illustration Section */}
          <div className="w-1/2 relative bg-gradient-to-r from-blue-500 to-indigo-500 flex items-center justify-center">
            <Image
              src="/login-illustration.png"
              alt="Login Illustration"
              fill
              className="object-cover"
            />
          </div>

          {/* Form Section */}
          <div className="w-1/2 p-10 bg-white text-gray-700">
            <div className="text-center mb-6">
              <div className="flex items-center justify-center space-x-2">
                <svg
                  className="w-6 h-6 text-blue-600"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                >
                  <path d="M12 2a10 10 0 00-3.16 19.45c.5.09.68-.22.68-.48v-1.68c-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.1-1.47-1.1-1.47-.9-.63.07-.62.07-.62 1 .07 1.53 1.02 1.53 1.02.89 1.52 2.34 1.08 2.9.83.09-.65.35-1.08.63-1.33-2.22-.25-4.56-1.11-4.56-4.95 0-1.09.39-1.98 1.02-2.68-.1-.25-.44-1.27.1-2.65 0 0 .84-.27 2.75 1.02a9.54 9.54 0 015 0C15.93 7.7 16.77 8 16.77 8c.54 1.38.2 2.4.1 2.65.63.7 1.02 1.59 1.02 2.68 0 3.85-2.34 4.7-4.57 4.94.36.3.68.89.68 1.79v2.65c0 .27.18.58.69.48A10.01 10.01 0 0012 2z" />
                </svg>
                <h2 className="text-2xl font-bold text-gray-700">Login</h2>
              </div>
            </div>

            {/* React Hook Form */}
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
              <div>
                <label
                  htmlFor="email"
                  className="block text-sm font-medium text-gray-700"
                >
                  Email
                </label>
                <input
                  type="email"
                  id="email"
                  placeholder="aman.m134@mail.com"
                  className="w-full mt-1 px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  {...register("email", { required: "Email is required" })}
                />
                {errors.email && (
                  <p className="text-red-500 text-sm">{errors.email.message}</p>
                )}
              </div>

              <div>
                <label
                  htmlFor="password"
                  className="block text-sm font-medium text-gray-700"
                >
                  Password
                </label>
                <input
                  type="password"
                  id="password"
                  placeholder="********"
                  className="w-full mt-1 px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  {...register("password", {
                    required: "Password is required",
                  })}
                />
                {errors.password && (
                  <p className="text-red-500 text-sm">
                    {errors.password.message}
                  </p>
                )}
              </div>

              <div className="text-right">
                <a href="#" className="text-sm text-blue-600 hover:underline">
                  Forgot Password?
                </a>
              </div>

              <button
                type="submit"
                className="w-full py-2 text-white bg-gradient-to-r from-blue-500 to-indigo-500 rounded-md hover:opacity-90 transition"
              >
                LOGIN
              </button>

              {error && <p className="text-red-500 text-sm">{error}</p>}
            </form>
          </div>
        </div>
      </div>
    </>
  );
}
