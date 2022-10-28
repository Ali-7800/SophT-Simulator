import click
import elastica as ea
import numpy as np
import os
from sopht.utils.IO import IO
from sopht.utils.precision import get_real_t
import sopht_simulator as sps


def flow_past_sphere_case(
    grid_size,
    num_forcing_points_along_equator,
    reynolds=100.0,
    coupling_stiffness=-6e5,
    coupling_damping=-3.5e2,
    num_threads=4,
    precision="single",
    save_data=False,
):
    """
    This example considers the case of flow past a sphere in 3D.
    """
    dim = 3
    real_t = get_real_t(precision)
    x_range = 1.0
    far_field_velocity = 1.0
    grid_size_z, grid_size_y, grid_size_x = grid_size
    sphere_diameter = 0.4 * min(grid_size_z, grid_size_y) / grid_size_x * x_range
    nu = far_field_velocity * sphere_diameter / reynolds
    flow_sim = sps.UnboundedFlowSimulator3D(
        grid_size=grid_size,
        x_range=x_range,
        kinematic_viscosity=nu,
        real_t=real_t,
        num_threads=num_threads,
        flow_type="navier_stokes_with_forcing",
        with_free_stream_flow=True,
        navier_stokes_inertial_term_form="rotational",
    )
    rho_f = 1.0
    sphere_projected_area = 0.25 * np.pi * sphere_diameter**2
    drag_force_scale = 0.5 * rho_f * far_field_velocity**2 * sphere_projected_area

    # Initialize velocity = c in X direction
    velocity_free_stream = np.array([far_field_velocity, 0.0, 0.0])

    # Initialize fixed sphere (elastica rigid body)
    X_cm = 0.25 * flow_sim.x_range
    Y_cm = 0.5 * flow_sim.y_range
    Z_cm = 0.5 * flow_sim.z_range
    sphere_com = np.array([X_cm, Y_cm, Z_cm])
    density = 1e3
    sphere = ea.Sphere(
        center=sphere_com, base_radius=(sphere_diameter / 2.0), density=density
    )
    # Since the sphere is fixed, we don't add it to pyelastica simulator,
    # and directly use it for setting up the flow interactor.
    # ==================FLOW-BODY COMMUNICATOR SETUP START======
    sphere_flow_interactor = sps.RigidBodyFlowInteraction(
        rigid_body=sphere,
        eul_grid_forcing_field=flow_sim.eul_grid_forcing_field,
        eul_grid_velocity_field=flow_sim.velocity_field,
        virtual_boundary_stiffness_coeff=coupling_stiffness,
        virtual_boundary_damping_coeff=coupling_damping,
        dx=flow_sim.dx,
        grid_dim=dim,
        real_t=real_t,
        forcing_grid_cls=sps.SphereForcingGrid,
        num_forcing_points_along_equator=num_forcing_points_along_equator,
    )
    # ==================FLOW-BODY COMMUNICATOR SETUP END======

    if save_data:
        # setup IO
        # TODO internalise this in flow simulator as dump_fields
        io_origin = np.array(
            [flow_sim.z_grid.min(), flow_sim.y_grid.min(), flow_sim.x_grid.min()]
        )
        io_dx = flow_sim.dx * np.ones(dim)
        io_grid_size = np.array(grid_size)
        io = IO(dim=dim, real_dtype=real_t)
        io.define_eulerian_grid(origin=io_origin, dx=io_dx, grid_size=io_grid_size)
        io.add_as_eulerian_fields_for_io(
            vorticity=flow_sim.vorticity_field, velocity=flow_sim.velocity_field
        )
        # Initialize sphere IO
        sphere_io = IO(dim=dim, real_dtype=real_t)
        # Add vector field on lagrangian grid
        sphere_io.add_as_lagrangian_fields_for_io(
            lagrangian_grid=sphere_flow_interactor.forcing_grid.position_field,
            lagrangian_grid_name="sphere",
            vector_3d=sphere_flow_interactor.lag_grid_forcing_field,
        )

    t = 0.0
    timescale = sphere_diameter / far_field_velocity
    t_end_hat = 10.0  # non-dimensional end time
    t_end = t_end_hat * timescale  # dimensional end time
    foto_timer = 0.0
    foto_timer_limit = t_end / 40
    time = []
    drag_coeffs = []

    # create fig for plotting flow fields
    fig, ax = sps.create_figure_and_axes()

    # iterate
    while t < t_end:
        # Save data
        if foto_timer > foto_timer_limit or foto_timer == 0:
            foto_timer = 0.0
            # calculate drag
            x_axis = 0
            drag_force = np.fabs(
                np.sum(sphere_flow_interactor.lag_grid_forcing_field[x_axis, ...])
            )
            drag_coeff = drag_force / drag_force_scale
            time.append(t)
            drag_coeffs.append(drag_coeff)
            if save_data:
                io.save(
                    h5_file_name="sopht_" + str("%0.4d" % (t * 100)) + ".h5", time=t
                )
                sphere_io.save(
                    h5_file_name="sphere_" + str("%0.4d" % (t * 100)) + ".h5", time=t
                )
            ax.set_title(f"Velocity X comp, time: {t / timescale:.2f}")
            contourf_obj = ax.contourf(
                flow_sim.x_grid[:, grid_size_y // 2, :],
                flow_sim.z_grid[:, grid_size_y // 2, :],
                np.mean(
                    flow_sim.velocity_field[
                        0, :, grid_size_y // 2 - 1 : grid_size_y // 2 + 1, :
                    ],
                    axis=1,
                ),
                levels=50,
                extend="both",
                cmap=sps.lab_cmap,
            )
            cbar = fig.colorbar(mappable=contourf_obj, ax=ax)
            ax.scatter(
                sphere_flow_interactor.forcing_grid.position_field[0],
                sphere_flow_interactor.forcing_grid.position_field[2],
                s=5,
                color="k",
            )
            sps.save_and_clear_fig(
                fig, ax, cbar, file_name="snap_" + str("%0.4d" % (t * 100)) + ".png"
            )
            print(
                f"time: {t:.2f} ({(t/t_end*100):2.1f}%), "
                f"max_vort: {np.amax(flow_sim.vorticity_field):.4f}, "
                f"drag coeff: {drag_coeff:.4f}, "
                f"div vorticity norm: {flow_sim.get_vorticity_divergence_l2_norm():.4f}"
            )

        dt = flow_sim.compute_stable_timestep(dt_prefac=0.25)

        # compute flow forcing and timestep forcing
        sphere_flow_interactor.time_step(dt=dt)
        sphere_flow_interactor()

        flow_sim.time_step(dt=dt, free_stream_velocity=velocity_free_stream)

        # update timers
        t = t + dt
        foto_timer += dt

    fig, ax = sps.create_figure_and_axes(fig_aspect_ratio="default")
    ax.plot(np.array(time), np.array(drag_coeffs), label="numerical")
    ax.set_xlabel("Time")
    ax.set_ylabel("Drag coefficient")
    fig.savefig("drag_coeff_vs_time.png")
    np.savetxt(
        "drag_vs_time.csv",
        np.c_[np.array(time), np.array(drag_coeffs)],
        delimiter=",",
        header="time, drag_coeff",
    )

    os.system("rm -f flow.mp4")
    os.system(
        "ffmpeg -r 10 -s 3840x2160 -f image2 -pattern_type glob -i 'snap*.png' "
        "-vcodec libx264 -crf 15 -pix_fmt yuv420p -vf 'crop=trunc(iw/2)*2:trunc(ih/2)*2'"
        " flow.mp4"
    )
    os.system("rm -f snap*.png")


if __name__ == "__main__":

    @click.command()
    @click.option("--num_threads", default=4, help="Number of threads for parallelism.")
    @click.option("--nx", default=128, help="Number of grid points in x direction.")
    def simulate_parallelised_flow_past_sphere(num_threads, nx):
        ny = nx // 2
        nz = nx // 2
        # in order Z, Y, X
        grid_size = (nz, ny, nx)
        num_forcing_points_along_equator = 3 * (nx // 8)

        click.echo(f"Number of threads for parallelism: {num_threads, }")
        click.echo(f"Grid size:  {nz, ny, nx ,} ")
        click.echo(
            f"num forcing points along equator:  {num_forcing_points_along_equator}"
        )
        flow_past_sphere_case(
            grid_size=grid_size,
            num_forcing_points_along_equator=num_forcing_points_along_equator,
            num_threads=num_threads,
            save_data=False,
        )

    simulate_parallelised_flow_past_sphere()
