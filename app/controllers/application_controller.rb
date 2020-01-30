class ApplicationController < ActionController::Base
  include Passwordless::ControllerHelpers

  before_action :show_default_name_notice
  helper_method :current_user

  private

  def current_user
    @current_user ||= authenticate_by_cookie(User)
  end

  def require_user!
    if current_user
      if current_user.deactivated?
        redirect_to root_path, flash: {
          error: "It looks like #{current_user.email} is no longer a Boston Worts member. Extend your membership so you can post your trophies!"
        }
      end
    else
      save_passwordless_redirect_location!(User)
      redirect_to users.sign_in_path, flash: {
        error: "Hi! You must log in as a Boston Worts member to do this. Enter your email address and we'll send you a link to log in."
      }
    end
  end

  def show_default_name_notice
    if current_user&.has_default_name?
      flash.now[:notice] = "Please update your name by <a href='#{edit_my_profile_path}'>editing your profile</a>"
    end
  end
end
