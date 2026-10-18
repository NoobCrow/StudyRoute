import { z } from "zod";

/** Shared by the sign-in form and its tests. */
export const signInSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "Enter your email.")
    .pipe(z.string().email("Enter a valid email address.")),
  password: z.string().min(1, "Enter your password."),
});

export type SignInValues = z.infer<typeof signInSchema>;
