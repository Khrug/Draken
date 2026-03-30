import numpy as np
import matplotlib.pyplot as plt

from numpy.linalg import norm, eigvalsh

# -----------------------------
# World (2D) with vector-field terrain
# -----------------------------
class World2D:
    def __init__(self, steps, dt=0.1, energy_budget=120.0, noise_std=0.35, seed=0):
        self.steps = int(steps)
        self.dt = float(dt)
        self.energy = float(energy_budget)
        self.noise_std = float(noise_std)
        self.rng = np.random.default_rng(seed)

        t = np.linspace(0, 4*np.pi, self.steps)
        # Minimal 2D "swirl-ish" drift field: sin/cos as orthogonal components
        self.terrain = np.stack([np.sin(t), np.cos(t)], axis=0)  # shape (2, steps)

        self.t = 0
        self.x = np.zeros(2, dtype=float)

    def step(self, action_2d):
        a = np.array(action_2d, dtype=float).reshape(2,)
        # Thermodynamic cost: baseline + proportional to action magnitude
        cost = 0.4 + 1.6 * norm(a)

        if cost > self.energy:
            # Energy-death
            return False, self.x.copy(), np.zeros(2), np.zeros(2)

        drift = self.terrain[:, self.t] * self.dt
        noise = self.rng.normal(0.0, self.noise_std, size=2)

        prev = self.x.copy()
        self.x = self.x + drift + (a * self.dt) + noise
        self.energy -= cost

        self.t = min(self.t + 1, self.steps - 1)

        world_delta = self.x - prev
        return True, self.x.copy(), noise, drift


# -----------------------------
# Trotskij Observer (2D): lagged/noisy "partner stream"
# -----------------------------
class TrotskijObserver2D:
    def __init__(self, init_x=None, lag=3.0, obs_noise_std=0.15, seed=1):
        self.x = np.zeros(2, dtype=float) if init_x is None else np.array(init_x, dtype=float).reshape(2,)
        self.lag = float(lag)
        self.obs_noise_std = float(obs_noise_std)
        self.rng = np.random.default_rng(seed)

    def step(self, world_x_2d):
        wx = np.array(world_x_2d, dtype=float).reshape(2,)
        # First-order lag dynamics + observation noise
        self.x += (wx - self.x) / max(self.lag, 1e-9)
        self.x += self.rng.normal(0.0, self.obs_noise_std, size=2)
        return self.x.copy()


# -----------------------------
# Holon: resonance channel + winter mechanism (scalar resonance, tensor-based mismatch)
# -----------------------------
class Holon:
    def __init__(self, epsilon=0.5, var_threshold=0.03, winter_steps=7, mismatch_scale=0.25,
                 winter_var_shrink=0.85):
        self.epsilon = float(epsilon)
        self.var_threshold = float(var_threshold)
        self.winter_steps = int(winter_steps)
        self.mismatch_scale = float(mismatch_scale)
        self.winter_var_shrink = float(winter_var_shrink)

        self.m_var = 0.0
        self._winter_remaining = 0
        self.gorba_ready = False

    def in_winter(self):
        return self._winter_remaining > 0

    def trigger_winter(self):
        self._winter_remaining = self.winter_steps

    @staticmethod
    def mismatch_to_resonance(mismatch, scale):
        # Bounded in (0,1], monotone decreasing
        s = max(float(scale), 1e-9)
        return 1.0 / (1.0 + (float(mismatch) / s))

    def update_variance(self, mismatch, alpha=0.05):
        # EWMA of mismatch^2
        mm2 = float(mismatch) ** 2
        self.m_var = (1 - alpha) * self.m_var + alpha * mm2

    def tick_winter(self):
        if self._winter_remaining > 0:
            self._winter_remaining -= 1
            # Winter "compression": shrink variance estimate
            self.m_var *= self.winter_var_shrink

            # If winter ends and variance is safely low -> Gorba lock becomes available
            if self._winter_remaining == 0 and self.m_var < (0.8 * self.var_threshold):
                self.gorba_ready = True

    def should_trigger_winter(self):
        return self.m_var > self.var_threshold


# -----------------------------
# Agent: 2D planner + Monte Carlo viability checks + Gorba lock
# -----------------------------
class Agent2D:
    def __init__(self, omega_point=(5.0, 5.0), action_cap=6.0, viability_p=0.7,
                 ctrl_noise_base=0.15):
        self.omega = np.array(omega_point, dtype=float).reshape(2,)
        self.action_cap = float(action_cap)
        self.viability_p = float(viability_p)
        self.ctrl_noise_base = float(ctrl_noise_base)

        # Noise estimators (2D abs + 2x2 covariance)
        self.noise_abs_est = np.array([0.35, 0.35], dtype=float)
        self.noise_cov_est = np.eye(2) * (0.35**2)

        # Gorba (one-way stability lock)
        self.gorba_active = False
        self.ctrl_noise_reduction = 0.7  # reduce rollout control noise when Gorba active

    def update_noise_estimate(self, noise_sample_2d, alpha=0.05):
        if self.gorba_active:
            return  # frozen under Gorba
        n = np.array(noise_sample_2d, dtype=float).reshape(2,)
        self.noise_abs_est = (1 - alpha) * self.noise_abs_est + alpha * np.abs(n)
        self.noise_cov_est = (1 - alpha) * self.noise_cov_est + alpha * np.outer(n, n)

    def _ctrl_noise_std(self, assumed_noise_std):
        # Use max eigenvalue of covariance as a scalar "uncertainty radius"
        lam_max = float(np.max(eigvalsh(self.noise_cov_est)))
        base = self.ctrl_noise_base * float(assumed_noise_std)
        # softly modulate by estimated covariance (kept minimal)
        mod = np.clip(np.sqrt(lam_max) / (assumed_noise_std + 1e-9), 0.5, 2.0)
        ctrl = base * mod
        if self.gorba_active:
            ctrl *= self.ctrl_noise_reduction
        return float(ctrl)

    def _estimate_terminal_viability(self, x_agent, x_world, remaining_steps, dt, assumed_noise_std,
                                    n_rollouts=24, terminal_tol=0.7, ctrl_policy_mix=(0.6, 0.4), rng=None):
        """
        Minimal retrocausal proxy: accept action only if futures (MC rollouts) reach omega with enough probability.
        """
        if rng is None:
            rng = np.random.default_rng(0)

        xa0 = np.array(x_agent, dtype=float).reshape(2,)
        xw0 = np.array(x_world, dtype=float).reshape(2,)

        if remaining_steps <= 0:
            return 1.0 if norm(xa0 - self.omega) <= terminal_tol else 0.0

        ctrl_noise_std = self._ctrl_noise_std(assumed_noise_std)
        w_future, w_local = ctrl_policy_mix

        successes = 0
        for _ in range(n_rollouts):
            xa = xa0.copy()
            xw = xw0.copy()

            for k in range(remaining_steps):
                denom = max(1, (remaining_steps - k))
                future_pull = (self.omega - xa) / denom
                local_push = (xw - xa)

                # Conservative tail policy
                a = (w_future * future_pull + w_local * local_push) / max(dt, 1e-9)
                a = np.clip(a, -self.action_cap, self.action_cap)

                # Control noise + world noise
                a += rng.normal(0.0, ctrl_noise_std, size=2)
                w_noise = rng.normal(0.0, assumed_noise_std, size=2)

                # World drift omitted in rollout tail (kept minimal & conservative)
                xa = xa + a * dt
                xw = xw + w_noise

            if norm(xa - self.omega) <= terminal_tol:
                successes += 1

        return successes / max(1, n_rollouts)

    def choose_action(self, x_agent, x_world, remaining_steps, dt, assumed_noise_std, energy,
                      in_winter=False, rng=None, verbose=False):
        """
        Pick an action that:
        - tracks world locally
        - moves toward omega
        - passes viability threshold in MC rollouts
        Winter: soft reduction of gain (not a full freeze).
        """
        if rng is None:
            rng = np.random.default_rng(0)

        xa = np.array(x_agent, dtype=float).reshape(2,)
        xw = np.array(x_world, dtype=float).reshape(2,)

        denom = max(1, remaining_steps)
        future_pull = (self.omega - xa) / denom
        local_push = (xw - xa)

        # Noise-aware weighting (minimal): if estimated noise is high, bias local tracking slightly
        noise_radius = norm(self.noise_abs_est)
        noise_factor = np.clip(noise_radius / (assumed_noise_std + 1e-9), 0.0, 3.0)
        w_local = 0.45 + 0.10 * noise_factor
        w_future = 1.0 - w_local

        ideal = (w_future * future_pull + w_local * local_push) / max(dt, 1e-9)
        ideal = np.clip(ideal, -self.action_cap, self.action_cap)

        # Winter softening
        gain = 0.25 if in_winter else 1.0
        ideal = ideal * gain

        # Candidate grid around ideal (81 candidates)
        deltas = np.array([-4, -2, -1, -0.5, 0.0, 0.5, 1, 2, 4], dtype=float)
        cand_x = np.clip(ideal[0] + deltas, -self.action_cap, self.action_cap)
        cand_y = np.clip(ideal[1] + deltas, -self.action_cap, self.action_cap)
        candidates = np.array(np.meshgrid(cand_x, cand_y)).T.reshape(-1, 2)

        # Filter feasible by energy cost (match World cost model)
        feasible = []
        for a in candidates:
            step_cost = 0.4 + 1.6 * norm(a)
            if step_cost <= energy:
                feasible.append(a.copy())

        if not feasible:
            return np.zeros(2), {"reason": "energy_no_step_feasible", "viability": 0.0}

        best = None
        best_score = -1e18
        best_viab = 0.0

        for a in feasible:
            # Immediate track score: prefer staying near world after applying action
            xa_next = xa + a * dt
            immediate_track = -norm(xa_next - xw)

            # Retrocausal viability score (MC)
            viab = self._estimate_terminal_viability(
                x_agent=xa_next,
                x_world=xw,
                remaining_steps=max(0, remaining_steps - 1),
                dt=dt,
                assumed_noise_std=assumed_noise_std,
                rng=rng
            )

            if viab < self.viability_p:
                continue

            # Combined score: prioritize viability, then tracking (kept minimal)
            score = 2.0 * viab + 0.2 * immediate_track

            if score > best_score:
                best_score = score
                best = a.copy()
                best_viab = viab

        if best is None:
            # No viable action found
            return np.zeros(2), {"reason": "no_viable_action", "viability": 0.0}

        return best, {"reason": "ok", "viability": float(best_viab)}


# -----------------------------
# Simulator: Dyadic Pearl in 2D + Gorba
# -----------------------------
class DrakenHandshakeSim2D:
    def __init__(self,
                 steps=140,
                 dt=0.1,
                 seed=2,
                 omega_point=(5.0, 5.0),
                 world_noise=0.35,
                 energy_budget=120.0,
                 tro_lag=3.0,
                 tro_noise=0.15,
                 epsilon=0.5,
                 mismatch_scale=0.25,
                 var_threshold=0.03,
                 winter_steps=7,
                 hard_winter=False,
                 divergence_limit=None,
                 viability_p=0.7):

        self.steps = int(steps)
        self.dt = float(dt)
        self.seed = int(seed)
        self.rng = np.random.default_rng(seed)

        self.world = World2D(steps=self.steps, dt=self.dt, energy_budget=energy_budget, noise_std=world_noise, seed=seed)
        self.trotskij = TrotskijObserver2D(init_x=np.zeros(2), lag=tro_lag, obs_noise_std=tro_noise, seed=seed+1)

        self.holon = Holon(epsilon=epsilon, var_threshold=var_threshold, winter_steps=winter_steps,
                           mismatch_scale=mismatch_scale, winter_var_shrink=0.85)
        self.agent = Agent2D(omega_point=omega_point, viability_p=viability_p)

        self.hard_winter = bool(hard_winter)
        self.divergence_limit = divergence_limit  # if None: holon governs

        # State traces
        self.world_state = np.zeros((self.steps, 2))
        self.agent_state = np.zeros((self.steps, 2))
        self.tro_state = np.zeros((self.steps, 2))
        self.resonance = np.zeros(self.steps)
        self.mismatch = np.zeros(self.steps)
        self.energy = np.zeros(self.steps)
        self.in_winter = np.zeros(self.steps, dtype=bool)
        self.gorba_active = np.zeros(self.steps, dtype=bool)

    @staticmethod
    def _strain_tensor(delta_2d):
        d = np.array(delta_2d, dtype=float).reshape(2,)
        return np.outer(d, d)  # 2x2

    def run(self, verbose=True):
        if verbose:
            print("Initializing Draken Handshake Simulator — v0.3 2D Tensor Pearl + Gorba")
            print(f"  Steps={self.steps}, dt={self.dt}, Omega={self.agent.omega}, seed={self.seed}")
            print(f"  World noise={self.world.noise_std}, Energy={self.world.energy}")
            print(f"  Trotskij lag={self.trotskij.lag}, Trotskij obs noise={self.trotskij.obs_noise_std}")
            print(f"  Holon ε={self.holon.epsilon}, var_th={self.holon.var_threshold}, winter_steps={self.holon.winter_steps}, hard_winter={self.hard_winter}")
            print(f"  Divergence guard: {'enabled' if self.divergence_limit is not None else 'disabled (holon governs)'}")

        # init
        xa = np.zeros(2)
        xt = np.zeros(2)

        for t in range(self.steps - 1):
            self.world_state[t] = self.world.x
            self.agent_state[t] = xa
            self.tro_state[t] = xt
            self.energy[t] = self.world.energy
            self.gorba_active[t] = self.agent.gorba_active

            # Determine winter state (note: tick_winter happens each step)
            in_w = self.holon.in_winter()
            self.in_winter[t] = in_w

            # Agent chooses action
            if in_w and self.hard_winter:
                action = np.zeros(2)
                meta = {"reason": "hard_winter_freeze", "viability": 0.0}
            else:
                action, meta = self.agent.choose_action(
                    x_agent=xa,
                    x_world=self.world.x,
                    remaining_steps=(self.steps - 1 - t),
                    dt=self.dt,
                    assumed_noise_std=self.world.noise_std,
                    energy=self.world.energy,
                    in_winter=in_w,
                    rng=self.rng
                )

            prev_world = self.world.x.copy()
            prev_tro = xt.copy()

            # Step world
            ok, xw, noise, drift = self.world.step(action)
            if not ok:
                if verbose:
                    print(f"💀 FAILURE @ t={t}: Energy depleted (thermodynamic death).")
                return "Failure: Energy depleted", t

            # Update Trotskij stream
            xt = self.trotskij.step(xw)

            # Update agent estimate of noise (unless Gorba is active)
            self.agent.update_noise_estimate(noise_sample_2d=noise, alpha=0.05)

            # Build dyadic deltas
            predicted_delta = action * self.dt
            observed_delta = xw - prev_world
            tro_delta = xt - prev_tro
            consensus_delta = 0.5 * (observed_delta + tro_delta)

            # Tensor-binding mismatch: Frobenius norm of strain-tensor difference
            P = self._strain_tensor(predicted_delta)
            C = self._strain_tensor(consensus_delta)
            mismatch = norm(P - C, ord="fro")

            # Holon update: resonance from mismatch
            r = self.holon.mismatch_to_resonance(mismatch, scale=self.holon.mismatch_scale)
            self.mismatch[t] = mismatch
            self.resonance[t] = r

            # Update holon mismatch variance
            # In winter, we can consolidate faster (slightly higher alpha) without "cheating"
            alpha_var = 0.10 if in_w else 0.05
            self.holon.update_variance(mismatch=mismatch, alpha=alpha_var)

            # Trigger winter if variance too high (and not already in winter)
            if (not self.holon.in_winter()) and self.holon.should_trigger_winter():
                self.holon.trigger_winter()

            # Tick winter (shrink variance, maybe set gorba_ready)
            self.holon.tick_winter()

            # Gorba lock: one-way stability phase after successful winter
            if (not self.holon.in_winter()) and self.holon.gorba_ready and (not self.agent.gorba_active):
                self.agent.gorba_active = True
                self.holon.gorba_ready = False
                if verbose:
                    print(f"🔒 GORBA ACTIVATED @ t={t}: noise_abs_est & cov frozen; rollout ctrl-noise reduced.")

            # Failure: holon below epsilon (semantic decoupling)
            if r < self.holon.epsilon:
                if verbose:
                    print(f"💔 FAILURE @ t={t}: Holon resonance below ε. r={r:.3f}")
                return "Failure: Holon below epsilon", t

            # Optional divergence guard (norm-based in 2D)
            xa_next = xa + action * self.dt
            if self.divergence_limit is not None:
                if norm(xa_next - xw) > float(self.divergence_limit):
                    if verbose:
                        print(f"🧯 FAILURE @ t={t}: Divergence guard tripped. ||agent-world||={norm(xa_next-xw):.3f}")
                    return "Failure: Divergence guard", t

            # Apply agent action (agent state)
            xa = xa_next

        # record last
        self.world_state[-1] = self.world.x
        self.agent_state[-1] = xa
        self.tro_state[-1] = xt
        self.energy[-1] = self.world.energy
        self.gorba_active[-1] = self.agent.gorba_active

        # Terminal viability check (2D norm)
        terminal_tol = 0.7
        if norm(xa - self.agent.omega) > terminal_tol:
            if verbose:
                print(f"⚠️ FAILURE: Terminal constraint not satisfied. ||agent-omega||={norm(xa-self.agent.omega):.3f}")
            return "Failure: Terminal constraint not satisfied", self.steps - 1

        if verbose:
            print("✅ SUCCESS: Terminal viability satisfied.")
        return "Success", self.steps - 1

    def visualize(self):
        t = np.arange(self.steps)

        # Plot x-dimension
        plt.figure(figsize=(11, 4))
        plt.plot(t, self.world_state[:, 0], label="World x", alpha=0.7)
        plt.plot(t, self.agent_state[:, 0], label="Agent x", alpha=0.9)
        plt.plot(t, self.tro_state[:, 0], label="Trotskij x", alpha=0.7)
        plt.axhline(self.agent.omega[0], linestyle="--", label="Omega x")
        plt.title("2D Dyadic Pearl — X dimension")
        plt.xlabel("t")
        plt.ylabel("x")
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.show()

        # Plot y-dimension
        plt.figure(figsize=(11, 4))
        plt.plot(t, self.world_state[:, 1], label="World y", alpha=0.7)
        plt.plot(t, self.agent_state[:, 1], label="Agent y", alpha=0.9)
        plt.plot(t, self.tro_state[:, 1], label="Trotskij y", alpha=0.7)
        plt.axhline(self.agent.omega[1], linestyle="--", label="Omega y")
        plt.title("2D Dyadic Pearl — Y dimension")
        plt.xlabel("t")
        plt.ylabel("y")
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.show()

        # Resonance + winter/gorba markers
        plt.figure(figsize=(11, 4))
        plt.plot(t, self.resonance, label="Resonance r(t)", alpha=0.9)
        plt.axhline(self.holon.epsilon, linestyle="--", label="ε threshold", alpha=0.8)
        # winter shading
        for i in range(self.steps):
            if self.in_winter[i]:
                plt.axvspan(i-0.5, i+0.5, alpha=0.08)
        # gorba markers
        gorba_idxs = np.where(self.gorba_active)[0]
        if len(gorba_idxs) > 0:
            plt.scatter(gorba_idxs, self.resonance[gorba_idxs], marker="o", label="Gorba active", s=18)

        plt.title("Holon resonance with Winter shading and Gorba activation")
        plt.xlabel("t")
        plt.ylabel("r")
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.show()


if __name__ == "__main__":
    sim = DrakenHandshakeSim2D(
        steps=140,
        dt=0.1,
        seed=2,
        omega_point=(5.0, 5.0),
        world_noise=0.35,
        energy_budget=120.0,
        tro_lag=3.0,
        tro_noise=0.15,
        epsilon=0.5,
        mismatch_scale=0.25,
        var_threshold=0.03,
        winter_steps=7,
        hard_winter=False,
        divergence_limit=None,
        viability_p=0.7
    )

    result, t_end = sim.run(verbose=True)
    print("Result:", result, "| t_end:", t_end)
    sim.visualize()
